#!/usr/bin/env python
import gdb
import os
import sys
import struct
from subprocess import call
import subprocess
import glob

""" ktest file version """
version_no = 3

debug = False
autobuild = True

debug_file = "resource"

klee_out_folder = 'target/x86_64-unknown-linux-gnu/debug/examples/'
stm_out_folder = 'target/thumbv7em-none-eabihf/release/examples/'

file_list = []
file_index_current = 0
object_index_current = 0


tasks = []
task_to_test = 0

task_name = ""

# Name, Cyccnt, ceiling
outputdata = []

init_done = 0
enable_output = 0

""" Max number of events guard """
object_index_max = 100

""" Define the original working directory """
original_pwd = os.getcwd()


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
        global enable_output

        print("Breakpoint location: %s" % self.location)

        if self.location == "idle":
            print("Reached IDLE")
            """
            When reaching idle() it means all the stubs
            has been executed and finished.

            Enable output measurements and then proceed calling the
            tasks
            """

            """
            Prepare the cycle counter
            """
            gdb_cyccnt_enable()
            gdb_cyccnt_reset()

            enable_output = 1
            gdb.prompt_hook = prompt
            return True

        """
        Needed to actually stop after the breakpoint
            True: Return prompt
            False: Continue?
        """
        return True
        # return False


# Subscribing to the stop events
def stop_event(evt):
    # print("#### stop event")
    # print("evt %r" % evt)
    """
    Every time a breakpoint is hit this function is executed

    The MainBP class will also be executed

    """

    global outputdata
    global task_name
    global file_index_current
    global file_list
    global enable_output

    file_name = file_list[file_index_current].split('/')[-1]
    """
    Get the current ceiling level, cast it to an integer
    """
    try:
        ceiling = int(gdb.parse_and_eval("ceiling").
                      cast(gdb.lookup_type('u8')))
    except gdb.error:

        """
        If there is no ceiling, it means we have returned to main
        since every claim have ceiling
        """
        if enable_output:
            outputdata.append([file_name, task_name,
                               gdb_cyccnt_read(), 0, "Finish"])
            gdb_cyccnt_reset()

        if file_index_current < len(file_list) - 1:
            gather_data()
        else:
            offset = 1
            print("\nFinished all ktest files!\n")
            print("Claims:")
            for index, obj in enumerate(outputdata):
                if obj[4] == "Exit":
                    claim_time = (obj[2] -
                                  outputdata[index - (offset)][2])
                    print("%s Claim time: %s" % (obj, claim_time))
                    offset += 2
                elif obj[4] == "Finish" and not obj[2] == 0:
                    offset = 1
                    tot_time = obj[2]
                    print("%s Total time: %s" % (obj, tot_time))
                else:
                    print("%s" % (obj))

            gdb.execute("quit")

        return

    """
    If outputdata is empty, we start
    If the same ceiling as previously: exit
    """
    # print("outputdata: %s" % outputdata)
    if enable_output:
        if len(outputdata):
            if outputdata[-1][3] >= ceiling:
                action = "Exit"
            else:
                action = "Enter"
        else:
            action = "Enter"

        cyccnt = gdb_cyccnt_read()
        outputdata.append([file_name, task_name, cyccnt, ceiling, action])

        print("CYCCNT:  %s\nCeiling: %s" % (cyccnt, outputdata[-1][3]))
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
    when the breakpoint at main() is hit

    Loads each defined task

    """

    """
    Subscribe stop_event to Breakpoint notifications
    """
    gdb.events.stop.connect(stop_event)

    print("Entering posted_event_init")

    global init_done
    global tasks
    global task_to_test
    global task_name
    global file_index_current
    global file_list
    global outputdata
    global enable_output

    """ Load the variable data """
    ktest_setdata(file_index_current)

    """
    If the number of the task is greater than the available tasks just finish
    """
    if task_to_test > len(tasks):
        print("Nothing to call...")
        init_done = 0
        file_index_current += 1
        gdb.post_event(posted_event_init)
        # gdb.post_event(gather_data)
        return

    # print("Tasks: ", tasks)
    # print("Name of task to test:", tasks[task_to_test])
    if not task_to_test == -1:
        """
        Before the call to the next task, reset the cycle counter
        """
        gdb_cyccnt_reset()

        file_name = file_list[file_index_current].split('/')[-1]
        task_name = tasks[task_to_test]

        if enable_output:
            outputdata.append([file_name, task_name,
                               gdb_cyccnt_read(), 0, "Start"])

        gdb.write('Task to call: %s \n' % (
                  tasks[task_to_test] + "()"))
        # gdb.prompt_hook = prompt
        gdb.execute('call %s' % "stub_" +
                    tasks[task_to_test] + "()")

        task_to_test = -1
        do_continue()
    else:
        print("Done else")


def gather_data():

    global outputdata
    global file_index_current
    global file_list
    global init_done

    """
    If not all ktest-files done yet, proceed
    """
    if file_index_current < len(file_list):
        init_done = 0
        file_index_current += 1
        # print("Current file: %s" % file_list[file_index_current])
        gdb.post_event(posted_event_init)

    else:
        print("Finished everything")

        print(outputdata)
        gdb.execute("quit")


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
                print(str)
            # if opts.writeInts and len(data) == 4:
            obj_data = struct.unpack('i', str)[0]
            if debug:
                print('object %4d: data: %r' %
                      (i, obj_data))
            # gdb.execute('whatis %r' % name.decode('UTF-8'))
            # gdb.execute('whatis %r' % obj_data)
            gdb.execute('set variable %s = %r' %
                        (example_name + "::" + name.decode('UTF-8'), obj_data))
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
    global debug
    global autobuild

    curdir = os.getcwd()
    if debug:
        print(curdir)

    rustoutputfolder = curdir + "/" + klee_out_folder
    try:
        os.chdir(rustoutputfolder)
    except IOError:
        print(rustoutputfolder + "not found. Need to run\n")
        print("xargo build --example " + example_name + " --features" +
              "klee_mode --target x86_64-unknown-linux-gnu ")
        print("\nand docker run --rm --user (id -u):(id -g)" +
              "-v $PWD" + "/" + klee_out_folder + ":/mnt" +
              "-w /mnt -it afoht/llvm-klee-4 /bin/bash ")
        if autobuild:
            xargo_run("klee")
            klee_run()
        else:
            print("Run the above commands before proceeding")
            sys.exit(1)

    if os.listdir(rustoutputfolder) == []:
        """
        The folder is empty, generate some files
        """
        xargo_run("klee")
        klee_run()

    dirlist = next(os.walk("."))[1]
    dirlist.sort()
    if debug:
        print(dirlist)

    if not dirlist:
        print("No KLEE output, need to run KLEE")
        print("Running klee...")
        klee_run()

    """ Ran KLEE, need to update the dirlist """
    dirlist = next(os.walk("."))[1]
    dirlist.sort()
    try:
        directory = dirlist[-1]
    except IOError:
        print("No KLEE output, need to run KLEE")
        print("Running klee...")
        klee_run()

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
    with open('klee/tasks.txt') as fin:
            for line in fin:
                # print(line)
                if not line == "// autogenerated file\n":
                    return [x.strip().strip("[]\"") for x in line.split(',')]


def xargo_run(mode):
    """
    Run xargo for building
    """

    if "klee" in mode:
        xargo_cmd = ("xargo build --example " + example_name + " --features " +
                     "klee_mode --target x86_64-unknown-linux-gnu ")
    elif "stm" in mode:
        xargo_cmd = ("xargo build --release --example " + example_name +
                     " --features " +
                     "wcet_bkpt --target thumbv7em-none-eabihf")
    else:
        print("Provide either 'klee' or 'stm' as mode")
        sys.exit(1)

    call(xargo_cmd, shell=True)


def klee_run():
    """
    Stub for running KLEE on the LLVM IR
    """
    global debug
    global original_pwd

    PWD = original_pwd

    user_id = subprocess.check_output(['id', '-u']).decode()
    group_id = subprocess.check_output(['id', '-g']).decode()

    bc_file = (glob.glob(PWD + "/" +
               klee_out_folder +
               '*.bc', recursive=False))[-1].split('/')[-1].strip('\'')
    if debug:
        print(PWD + "/" + klee_out_folder)
        print(bc_file)

    klee_cmd = ("docker run --rm --user " +
                user_id[:-1] + ":" + group_id[:-1] +
                " -v '"
                + PWD + "/"
                + klee_out_folder + "':'/mnt'" +
                " -w /mnt -it afoht/llvm-klee-4 " +
                "/bin/bash -c 'klee %s'" % bc_file)
    if debug:
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


"""Used for making GDB scriptable"""
gdb.execute("set confirm off")
gdb.execute("set pagination off")
gdb.execute("set verbose off")
gdb.execute("set height 0")

"""
Setup GDB for remote debugging
"""
gdb.execute("target remote :3333")
gdb.execute("monitor arm semihosting enable")

"""
Check if the user passed a file to use as the source.

If a file is given, use this as the example_name
"""
if gdb.progspaces()[0].filename:
    """ A filename was given on the gdb command line """
    example_name = gdb.progspaces()[0].filename.split('/')[-1]
    print("The resource used for debugging: %s" % example_name)
    try:
        os.path.exists(gdb.progspaces()[0].filename)
    except IOError:
        """ Compiles the given example """
        xargo_run("stm")
        xargo_run("klee")
else:
    example_name = debug_file
    print("Defaulting to example '%s' for debugging." % example_name)
    try:
        if example_name not in os.listdir(stm_out_folder):
            """ Compiles the default example """
            xargo_run("stm")
            xargo_run("klee")
    except IOError:
        """ Compiles the default example """
        xargo_run("stm")
        xargo_run("klee")

""" Tell GDB to load the file """
gdb.execute("file %s" % (stm_out_folder + example_name))
gdb.execute("load %s" % (stm_out_folder + example_name))

# gdb.execute("step")

""" Run KLEE on the generated files """
# print(klee_run())

""" Break at main to set variable values """
# AddBreakpoint("main")
# MainBP("main")
# MainBP("init")


""" Tell gdb-dashboard to hide """
# gdb.execute("dashboard -enabled off")
# gdb.execute("dashboard -output /dev/null")

""" Also break at the idle-loop """
MainBP("idle")

""" Save all ktest files into an array """
file_list = ktest_iterate()
# print(file_list)

""" Get all the tasks to jump to """
tasks = tasklist_get()
print("Available tasks:")
for t in tasks:
    print(t)

"""
Subscribe stop_event to Breakpoint notifications
"""
gdb.events.stop.connect(stop_event)

""" Run until the next breakpoint """
gdb.execute("c")
