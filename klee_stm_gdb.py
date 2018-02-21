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

file_list = []
file_index_current = 0
object_index_current = 0

tasks = []
task_to_test = -1

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


class MainBP(gdb.Breakpoint):

    global tasks

    def stop(self):
        # print("##### breakpoint")
        global file_index_current
        gdb.events.stop.connect(stop_event)
        if self.location == "init":
            gdb.write("Breakpoint in init()\n")
            gdb.prompt_hook = prompt
            gdb.post_event(posted_event_main)
            # gdb.execute('stop')
            # gdb.execute('jump %r' % tasks[0])

        elif self.location == "idle":
            """ Idle loop is reached, now jump to the task specified
                in the "task" value in the ktest files.

                If the task value is greater than the number of tasks,
                then run all of the tasks.

            """
            gdb.write("Breakpoint in loop()\n")
            gdb.prompt_hook = prompt

            print("Tasks: ", tasks)
            print("Name of task to test:", tasks[task_to_test])
            if not task_to_test == -1:
                gdb.write('Task to call: %s \n' % tasks[task_to_test])
                gdb.execute('call %s' % tasks[task_to_test])
            else:
                print("No task defined")
                """
                for task in tasks:
                    gdb.write('Task: %r \n' % task)
                    gdb.execute('jump %r' % task)
                """

            # gdb.write("Breakpoint in finish_execution\n")
            # gdb.write("Stopped before the main loop\n")
            """ Save the execution time and
                reload back to the main function.
            """
            gdb.prompt_hook = prompt
            gdb.post_event(posted_event_finish_execution)

        """ Needed to actually stop after the breakpoint """
        return True


# Subscribing to the stop events
def stop_event(evt):
    # print("#### stop event")
    # print("evt %r" % evt)
    gdb.events.stop.disconnect(stop_event)


# Hooking the prompt:
def prompt(current):
    # print("current %r" % current)
    # print("#### prompt")
    gdb.prompt_hook = current


# Posting events (which seem to work well when height=0)
# def posted_event():
    # print("#### posted event")
    # gdb.execute("


"""
Called when the breakpoint at main() is hit
"""


def posted_event_main():
    # print("# main BP")
    global file_index_current
    ktest_setdata(file_index_current)
    gdb.execute("continue")


def posted_event_finish_execution():
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
    b = KTest.fromfile(file_list[file_index])
    # print('ktest filename : %r' % filename)
    gdb.write('ktest file: %r \n' % file_list[file_index])
    # print('args       : %r' % b.args)
    # print('num objects: %r' % len(b.objects))
    for i, (name, data) in enumerate(b.objects):
        str = trimZeros(data)

        """ If Name is "task", skip it """
        if name.decode('UTF-8') == "task":
            print('object %4d: name: %r' % (i, name))
            print('object %4d: size: %r' % (i, len(data)))
            # print(struct.unpack('i', str).repr())
            # task_to_test = struct.unpack('i', str)[0]
            # print("str: ", str)
            # print("str: ", str[0])
            # task_to_test = struct.unpack('i', str)[0]
            task_to_test = int(str[0])
            print("Task to test:", task_to_test)
        else:
            print('object %4d: name: %r' % (i, name))
            print('object %4d: size: %r' % (i, len(data)))
            # if opts.writeInts and len(data) == 4:
            obj_data = struct.unpack('i', str)[0]
            print('object %4d: data: %r' %
                  (i, obj_data))
            # gdb.execute('whatis %r' % name.decode('UTF-8'))
            gdb.execute('whatis %r' % obj_data)
            gdb.execute('set variable %s = %r' %
                        (name.decode('UTF-8'), obj_data))
            # gdb.write('Variable %s is:' % name.decode('UTF-8'))
            # gdb.execute('print %s' % name.decode('UTF-8'))
            # else:
            # print('object %4d: data: %r' % (i, str))
    print("Done with setdata")


def ktest_iterate():
    """ Get the list of folders in current directory, sort and then grab the
        last one.
    """
    curdir = os.getcwd()
    print(curdir)
    """ We have already entered the output folder """
    rustoutputfolder = "../target/x86_64-unknown-linux-gnu/debug/examples/"
    try:
        os.chdir(rustoutputfolder)
    except IOError:
        print(rustoutputfolder + "not found. Need to run\n")
        print("xargo build --example resource --features\
              klee_mode --target x86_64-unknown-linux-gnu ")

    dirlist = next(os.walk("."))[1]
    dirlist.sort()
    print(dirlist)
    try:
        directory = dirlist[-1]
    except IOError:
        print("No KLEE output, need to run KLEE")

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

    print(os.getcwd())
    with open('../klee/tasks.txt') as fin:
            for line in fin:
                print(line)
                if not line == "// autogenerated file\n":
                    return [x.strip().strip("[]\"") for x in line.split(',')]


def klee_run():

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


""" Run KLEE on the generated files """
# print(klee_run())


""" Break at main to set variable values """
# AddBreakpoint("main")
MainBP("init")


""" Tell gdb-dashboard to hide """
gdb.execute("dashboard -enabled off")
gdb.execute("dashboard -output /dev/null")

""" Also break at the main-loop """
MainBP("idle")
# MainBP("terminate_execution")

"""Used for making it scriptable"""
gdb.execute("set confirm off")
gdb.execute("set pagination off")
gdb.execute("set verbose off")

""" Save all ktest files into an array """
file_list = ktest_iterate()
print(file_list)

""" Get all the tasks to jump to """
tasks = tasklist_get()
print(tasks)

""" Run until the main() breakpoint """
gdb.execute("c")
