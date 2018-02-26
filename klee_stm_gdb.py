import gdb
import os
import sys
import struct
import sqlite3
from subprocess import call
import subprocess

# Should ideally properly just import from ktest-tool
# from .ktesttool import KTest

version_no = 3

debug = False

file_list = []
file_index_current = 0
object_index_current = 0

tasks = []
task_to_test = 0

task_name = ""

# Name, Cyccnt, ceiling
outputdata = []

init_done = 0

""" Max number of events guard """
object_index_max = 100

database_name = "klee_profiling"
path = "output"

""" Create an folder named output if it doesn't exist """
os.makedirs(path, exist_ok=True)
""" Enter the output folder """
os.chdir(path)

""" Check if a database exists, otherwise create one """

if os.path.isfile("%s%s" % (database_name, ".db")):
    os.rename("%s%s" % (database_name, ".db"),
              "%s%s" % (database_name, "_old.db"))
    # conn = sqlite3.connect(database_name)
    # cur = conn.cursor()
    # print("Opened already created database")
conn = sqlite3.connect("%s%s" % (database_name, ".db"))
cur = conn.cursor()
cur.execute('''CREATE TABLE IF NOT EXISTS events
    (ID INTEGER PRIMARY KEY AUTOINCREMENT,
    FILE           TEXT     NOT NULL,
    TIME           INT      NOT NULL,
    RESOURCE       TEXT     NOT NULL,
    ACTION         TEXT,
    JOB            TEXT);''')


class KTestError(Exception):
    pass


class KTest:

    @staticmethod
    def fromfile(path):
        if not os.path.exists(path):
            print("ERROR: file %s not found" % (path))
            sys.exit(1)

        f = open(path, 'rb')
        hdr = f.read(5)
        if len(hdr) != 5 or (hdr != b'KTEST' and hdr != b"BOUT\n"):
            raise KTestError('unrecognized file')
        version, = struct.unpack('>i', f.read(4))
        if version > version_no:
            raise KTestError('unrecognized version')
        numArgs, = struct.unpack('>i', f.read(4))
        args = []
        for i in range(numArgs):
            size, = struct.unpack('>i', f.read(4))
            args.append(str(f.read(size).decode(encoding='ascii')))

        if version >= 2:
            symArgvs, = struct.unpack('>i', f.read(4))
            symArgvLen, = struct.unpack('>i', f.read(4))
        else:
            symArgvs = 0
            symArgvLen = 0

        numObjects, = struct.unpack('>i', f.read(4))
        objects = []
        for i in range(numObjects):
            size, = struct.unpack('>i', f.read(4))
            name = f.read(size)
            size, = struct.unpack('>i', f.read(4))
            bytes = f.read(size)
            objects.append((name, bytes))

        # Create an instance
        b = KTest(version, args, symArgvs, symArgvLen, objects)
        # Augment with extra filename field
        b.filename = path
        return b

    def __init__(self, version, args, symArgvs, symArgvLen, objects):
        self.version = version
        self.symArgvs = symArgvs
        self.symArgvLen = symArgvLen
        self.args = args
        self.objects = objects

        # add a field that represents the name of the program used to
        # generate this .ktest file:
        program_full_path = self.args[0]
        program_name = os.path.basename(program_full_path)
        # sometimes program names end in .bc, so strip them
        if program_name.endswith('.bc'):
            program_name = program_name[:-3]
        self.programName = program_name


def do_continue():
    gdb.execute("continue")


class MainBP(gdb.Breakpoint):

    def stop(self):
        global init_done

        if self.location == "init":

            if not init_done:
                # gdb.prompt_hook = prompt
                init_done = 1
                gdb.post_event(posted_event_init)
            else:
                gdb.post_event(gather_data)

        """ Needed to actually stop after the breakpoint
            True: Return prompt
            False: Continue?
        """
        return True
        # return False


# Subscribing to the stop events
def stop_event(evt):
    # print("#### stop event")
    # print("evt %r" % evt)

    global outputdata
    global task_name
    global file_index_current
    global file_list

    cyccnt = gdb_cyccnt_read()
    file_name = file_list[file_index_current].split('/')[-1]
    """
    Get the current ceiling level, cast it to an integer
    """
    try:
        ceiling = int(gdb.parse_and_eval("ceiling").
                      cast(gdb.lookup_type('u8')))
    except gdb.error:

        """
        If there is no ceiling, it means we have returned to init
        since every claim have ceiling
        """
        # gdb.events.stop.disconnect(stop_event)
        outputdata.append([file_name, task_name, cyccnt, 0, "Finish"])
        gdb_cyccnt_reset()

        if file_index_current < len(file_list) - 1:
            gather_data()
        else:
            print("\nFinished all ktest files!\n")
            print("Claims:")
            for x in outputdata:
                print("%s" % x)
            gdb.execute("quit")

        return

    print("CYCCNT:  %s\nCeiling: %s" % (cyccnt, outputdata[-1][3]))

    """
    If outputdata is empty, we start
    If the same ceiling as previously: exit
    """
    if len(outputdata):
        if outputdata[-1][3] >= ceiling:
            action = "Exit"
        else:
            action = "Enter"
    else:
        action = "Enter"

    outputdata.append([file_name, task_name, cyccnt, ceiling, action])

    """
    Prepare a prompt for do_continue()
    """
    gdb.prompt_hook = prompt
    do_continue()


# Hooking the prompt:
def prompt(current):
    # print("current %r" % current)
    # print("#### prompt")
    gdb.prompt_hook = current


# Posting events (which seem to work well when height=0)
# def posted_event():
    # print("#### posted event")
    # gdb.execute("


def posted_event_init():
    """
    Called at the very beginning of execution
    when the breakpoint at init() is hit

    Loads each defined task

    """

    """
    Subscribe stop_event to Breakpoint notifications
    """
    gdb.events.stop.connect(stop_event)

    # print("Entering posted_event_init")

    global tasks
    global task_to_test
    global task_name
    global file_index_current
    global file_list
    global outputdata

    """ Load the variable data """
    ktest_setdata(file_index_current)

    """
    Prepare the cycle counter
    """
    gdb_cyccnt_enable()
    gdb_cyccnt_reset()

    # print("Tasks: ", tasks)
    # print("Name of task to test:", tasks[task_to_test])

    if task_to_test > len(tasks):
        print("Nothing to call...")
        do_continue()
        return

    if not task_to_test == -1:
        task_name = tasks[task_to_test]
        file_name = file_list[file_index_current].split('/')[-1]
        outputdata.append([file_name, task_name, 0, 0, "Start"])

        gdb.write('Task to call: %s \n' % (
                  tasks[task_to_test] + "()"))
        # gdb.prompt_hook = prompt
        gdb.execute('call %s' % "stub_" +
                    tasks[task_to_test] + "()")
        # print("Called stub")

        task_to_test = -1
        do_continue()
    else:
        print("Done else")


def gather_data():

    global outputdata
    global file_index_current
    global file_list
    global init_done

    if file_index_current < len(file_list):
        init_done = 0
        file_index_current += 1
        # print("Current file: %s" % file_list[file_index_current])
        gdb.post_event(posted_event_init)

    else:
        print("Finished everything")

        print(outputdata)
        gdb.execute("quit")


def posted_event_finish_execution():
    """
    FIXME: Not used currently
    """

    """ Called when the breakpoint at finish_execution() is hit """
    global file_list
    global file_index_current
    global object_index_current
    global object_index_max

    # gdb.execute("print eventlist")

    # print("object_current: %r " % object_index_current)
    print("object_max: %r " % object_index_max)

    while object_index_current < object_index_max:
        """ Collect all data for the database """
        event_time = gdb.parse_and_eval("eventlist[" +
                                        str(object_index_current) +
                                        "].time")

        event_resource = gdb.parse_and_eval("eventlist[" +
                                            str(object_index_current) +
                                            "].elem")

        event_action = gdb.parse_and_eval("eventlist[" +
                                          str(object_index_current) +
                                          "].action")

        """ Parse which running job is active """

        event_job = gdb.parse_and_eval("job")

        """
        print("file: %r " % str(file_list[file_index_current]))
        print("time: %r " % int(event_time))
        print("resource:  %r" % str(event_resource))
        print("action:  %r" % str(event_action))
        """

        event = []

        event.append(str(file_list[file_index_current]))
        event.append(int(event_time))
        event.append(str(event_resource))
        event.append(str(event_action))
        event.append("j" + str(event_job))

        print("Event: %r " % event)

        try:
            cur = conn.cursor()

            cur.execute('INSERT INTO events(FILE, TIME, RESOURCE, ACTION, JOB)\
                        VALUES (?,?,?,?,?)', event)

        except sqlite3.Error as e:
            print("An error occurred:", e.args[0])

        object_index_current += 1
        """ If this was the END of execution go for next file """
        if str(event_action) == 'E':
            """ All events covered, break out from loop """
            break

    """ Reset object counter for next file """
    file_index_current += 1
    object_index_current = 0

    """ All done, commit to database and tidy after ourselves """
    if len(file_list) == file_index_current:
        print("Committing to database")
        conn.commit()

        conn.close()
        gdb.execute("quit")
    else:
        gdb.execute("run")


def trimZeros(str):
    for i in range(len(str))[::-1]:
        if str[i] != '\x00':
            return str[:i + 1]

    return ''


def ktest_setdata(file_index):
    """
    Substitute every variable found in ktest-file
    """
    global file_list
    global task_to_test
    global debug

    b = KTest.fromfile(file_list[file_index])
    if debug:
        # print('ktest filename : %r' % filename)
        gdb.write('ktest file: %r \n' % file_list[file_index])
        # print('args       : %r' % b.args)
        # print('num objects: %r' % len(b.objects))
    for i, (name, data) in enumerate(b.objects):
        str = trimZeros(data)

        """ If Name is "task", skip it """
        if name.decode('UTF-8') == "task":
            if debug:
                print('object %4d: name: %r' % (i, name))
                print('object %4d: size: %r' % (i, len(data)))
            # print(struct.unpack('i', str).repr())
            # task_to_test = struct.unpack('i', str)[0]
            # print("str: ", str)
            # print("str: ", str[0])
            task_to_test = struct.unpack('i', str)[0]
            # task_to_test = int(str[0])
            if debug:
                print("Task to test:", task_to_test)
        else:
            if debug:
                print('object %4d: name: %r' % (i, name))
                print('object %4d: size: %r' % (i, len(data)))
            # if opts.writeInts and len(data) == 4:
            obj_data = struct.unpack('i', str)[0]
            if debug:
                print('object %4d: data: %r' %
                      (i, obj_data))
            # gdb.execute('whatis %r' % name.decode('UTF-8'))
            # gdb.execute('whatis %r' % obj_data)
            gdb.execute('set variable %s = %r' %
                        (name.decode('UTF-8'), obj_data))
            # gdb.write('Variable %s is:' % name.decode('UTF-8'))
            # gdb.execute('print %s' % name.decode('UTF-8'))
            # else:
            # print('object %4d: data: %r' % (i, str))
    if debug:
        print("Done with setdata")


def ktest_iterate():
    """ Get the list of folders in current directory, sort and then grab the
        last one.
    """
    curdir = os.getcwd()
    if debug:
        print(curdir)
    """ We have already entered the output folder """
    rustoutputfolder = "../target/x86_64-unknown-linux-gnu/debug/examples/"
    try:
        os.chdir(rustoutputfolder)
    except IOError:
        print(rustoutputfolder + "not found. Need to run\n")
        print("xargo build --release --example resource --features\
              klee_mode --target x86_64-unknown-linux-gnu ")
        sys.exit(1)

    dirlist = next(os.walk("."))[1]
    dirlist.sort()
    if debug:
        print(dirlist)
    try:
        directory = dirlist[-1]
    except IOError:
        print("No KLEE output, need to run KLEE")
        sys.exit(1)

    print("Using ktest-files from directory:\n" + rustoutputfolder + directory)

    """ Iterate over all files ending with ktest in the "klee-last" folder """
    for filename in os.listdir(directory):
        if filename.endswith(".ktest"):
            file_list.append(os.path.join(rustoutputfolder + directory,
                                          filename))
        else:
            continue

    file_list.sort()
    """ Return to the old path """
    os.chdir(curdir)
    return file_list


def tasklist_get():
    """ Parse the automatically generated tasklist
    """

    if debug:
        print(os.getcwd())
    with open('../klee/tasks.txt') as fin:
            for line in fin:
                # print(line)
                if not line == "// autogenerated file\n":
                    return [x.strip().strip("[]\"") for x in line.split(',')]


def klee_run():
    """ Stub for running KLEE on the LLVM IR

    """
    PWD = os.getcwd()
    user_id = subprocess.check_output(['id', '-u']).decode()
    group_id = subprocess.check_output(['id', '-g']).decode()

    klee_cmd = ("docker run --rm --user " +
                user_id[:-1] + ":" + group_id[:-1] +
                " -v "
                + PWD
                + "/target/x86_64-unknown-linux-gnu/debug/examples:/mnt\
 -w /mnt -it afoht/llvm-klee-4 /bin/bash -c 'klee '*'.bc'")
    print(klee_cmd)
    call(klee_cmd, shell=True)


def gdb_cyccnt_enable():
    # Enable cyccnt
    gdb.execute("mon mww 0xe0001000 1")


def gdb_cyccnt_disable():
    # Disble cyccnt
    gdb.execute("mon mww 0xe0001000 0")


def gdb_cyccnt_reset():
    # Reset cycle counter to 0
    gdb.execute("mon mww 0xe0001004 0")


def gdb_cyccnt_read():
    # Read cycle counter
    return int(gdb.execute("mon mdw 0xe0001004", False, True).strip(
        '\n').strip('0xe000012004:').strip(',').strip(), 16)


def gdb_cyccnt_write(num):
    # Write to cycle counter
    gdb.execute('mon mww 0xe0001004 %r' % num)


""" Run KLEE on the generated files """
# print(klee_run())


""" Break at main to set variable values """
# AddBreakpoint("main")
MainBP("init")


""" Tell gdb-dashboard to hide """
# gdb.execute("dashboard -enabled off")
# gdb.execute("dashboard -output /dev/null")

""" Also break at the main-loop """
MainBP("idle")
# MainBP("terminate_execution")

"""Used for making it scriptable"""
gdb.execute("set confirm off")
gdb.execute("set pagination off")
gdb.execute("set verbose off")
gdb.execute("set height 0")

""" Save all ktest files into an array """
file_list = ktest_iterate()
# print(file_list)

""" Get all the tasks to jump to """
tasks = tasklist_get()
print("Available tasks:")
for t in tasks:
    print(t)

""" Run until the next breakpoint """
gdb.execute("c")
