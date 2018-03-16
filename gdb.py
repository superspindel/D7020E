#!/usr/bin/env python
import gdb
import os
import sys
import struct
from subprocess import call
import subprocess
import glob
import math

""" ktest file version """
version_no = 3

# debug = False
debug = True
autobuild = True

debug_file = "resource"

# klee_out_folder = 'target/x86_64-unknown-linux-gnu/debug/examples/'
klee_out_folder = 'target/x86_64-unknown-linux-gnu/release/examples/'
stm_out_folder = 'target/thumbv7em-none-eabihf/release/examples/'

file_list = []
file_index_current = -1
object_index_current = 0

tasks = []
priorities = []
interarrival = []

task_name = ""
file_name = ""

priority = 0
first = True

# [[ Test, Task, Cyccnt, priority/ceiling]]
outputdata = []

""" Max number of events guard """
object_index_max = 100

""" Define the original working directory """
original_pwd = os.getcwd()


""" taken from KLEE """


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

# Event handling

# Ugly hack to avoid race condtitons in the python gdb API


class Executor:
    def __init__(self, cmd):
        self.__cmd = cmd

    def __call__(self):
        gdb.execute(self.__cmd)


"""
Every time a breakpoint is hit this function is executed
"""


def stop_event(evt):
    global outputdata
    global task_name
    global priority
    global file_name

    imm = gdb_bkpt_read()
    if debug:
        print("Debug: stop event in file {}".format(file_name))
        print("Debug: evt %r" % evt)
        print("Debug: imm = {}".format(imm))

    if imm == 0:
        print("Ordinary breakpoint, exiting!")
        sys.exit(1)

    elif imm == 1 or imm == 2:
        try:
            ceiling = int(gdb.parse_and_eval(
                "ceiling").cast(gdb.lookup_type('u8')))
        except gdb.error:
            print("No ceiling found, exciting!")
            sys.exit(1)

        if imm == 1:
            action = "Enter"
        elif imm == 2:
            action = "Exit"

        if debug:
            print("Debug: Append action {} at cycle {}".format(
                action, gdb_cyccnt_read()))

        outputdata.append(
            [file_name, task_name, gdb_cyccnt_read(), ceiling, action])

        gdb.post_event(Executor("continue"))

    elif imm == 3:
        if debug:
            print("Debug: found finish bkpt_3 at cycle {}"
                  .format(gdb_cyccnt_read()))

        gdb.post_event(Executor("si"))

    elif imm == 4:
        if debug:
            print("Debug: found finish bkpt_4 at cycle {}"
                  .format(gdb_cyccnt_read()))

        gdb.post_event(posted_event_init)

    else:
        print("Unexpected stop event, exiting")
        sys.exit(1)


""" Loads each defined task """


def posted_event_init():
    if debug:
        print("\nDebug: Entering posted_event_init")

    global tasks
    global task_name
    global file_name
    global file_index_current
    global file_list
    global outputdata
    global priority
    global priorities

    if file_index_current < 0:
        if debug:
            print("Debug: Skipped first measurement")

    else:
        if debug:
            print("Debug: Append Finish action at cycle {}"
                  .format(gdb_cyccnt_read()))

        outputdata.append(
            [file_name, task_name, gdb_cyccnt_read(), priority, "Finish"])

    """ loop to skip to next task *omitting the dummy* """
    while True:
        file_index_current += 1
        if file_index_current == len(file_list):
            """ finished """
            break

        task_to_test = ktest_setdata(file_index_current)
        if 0 <= task_to_test < len(tasks):
            """ next """
            break

    if file_index_current < len(file_list):
        """ Load the variable data """

        if debug:
            print("Debug: Task number to test {}".format(task_to_test))

        """
        Before the call to the next task, reset the cycle counter
        """
        gdb_cyccnt_reset()

        file_name = file_list[file_index_current].split('/')[-1]
        task_name = tasks[task_to_test]
        priority = priorities[task_to_test]

        outputdata.append([file_name, task_name,
                           gdb_cyccnt_read(), priority, "Start"])

        print('Task to call: %s \n' % (
            tasks[task_to_test] + "()"))
        gdb.execute('call %s' % "stub_" +
                    tasks[task_to_test] + "()")

    else:
        claim_time_list = []
        """ here we are done, call your analysis here """
        offset = 1
        print("\nFinished all ktest files!\n")
        print("Claims:")
        for index, obj in enumerate(outputdata):
            if obj[4] == "Exit":
                claim_time = (obj[2] -
                              outputdata[index - (offset)][2])
                print("%s Claim time: %s" % (obj, claim_time))
                claim_time_list.append([obj[1], obj[3], claim_time]) # name, prio, claim_time
                offset += 2
            elif obj[4] == "Finish" and not obj[2] == 0:
                offset = 1
                tot_time = obj[2]
                print("%s Total time: %s" % (obj, tot_time))
            else:
                print("%s" % (obj))
        
        outputlist = calc_cpu(outputdata)
        calc_response(claim_time_list, outputlist)
        recursive_setup(claim_time_list, outputlist)
        # comment out to prevent gdb from quit on finish, useful to debugging
        gdb.execute("quit")

"""
    Calculate the CPU burden on the system, also returns a nicer outputlist from the outputdata array which contains all the neccessary data needed
    for further calculations in the assignments. Calculates CPU by checking total time of every task vs the interarrival time of the task and adding up.
    @input outputdata: The raw data from the tasks, including claims, exit and entering of these claims, starts and finishes of tasks and total times of tasks.
"""

def calc_cpu(outputdata):
    outputlist = []
    for outputline in outputdata: # Loop through data
        if outputline[4] == "Finish" and not outputline[2] == 0:
            new_line = [] # name, total_time, interval, priority
            new_line.append(outputline[1]) # Add name, example "EXTI1"
            new_line.append(outputline[2]) # Total time
            for task in tasklist_get():
                if task[0] == new_line[0]: # check task name vs name of the line of data that was read
                    new_line.append(task[2]) # interval time)
                    new_line.append(task[1]) # priority
            outputlist.append(new_line) # add task data to outputlist
    
    # remove duplicates
    new_list = []
    print(outputlist)
    for line in outputlist:
        if line[0] not in [x[0] for x in new_list]: # Check if name already in new_list
            new_list.append(line)
        else:
            duplicate = [x for x in new_list if x[0] == line[0]][0] # get the duplicate from new_list
            if line[1] > duplicate[1]: # check if total time is bigger
                new_list.remove(duplicate)
                new_list.append(line)

    # sort list for printout and further use of the list in response_time calculations, sorted based on min priority
    sorted_list = []
    while(len(new_list)>0):
        min_prio_task = new_list[0] # example task to have something to check agains
        for task in new_list:
            if task[3] < min_prio_task[3]: # check if new task has lower priority the previous min_prio_task
                min_prio_task = task
        sorted_list.append(min_prio_task) # add task to new sorted list
        new_list.remove(min_prio_task)    # remove from old list
    total = 0
    print ("\n ASSIGNMENT 2 \n")
    for item in sorted_list:
        print(str(item[0])+ " = "+str(item[1])+"/"+str(item[2]))
        total += int(item[1])/int(item[2]) # calculate CPU demand for each task and add to total
    print("---------------------")
    print(total)
    return sorted_list

"""
    Calculate the response time of the tasks in the outputlist as per the predefined calculation without recursion
    @input claim_time_list: the list of claims as gathered in the posted_event_init loop with [name, prio, claim_time] for every claim
    @input outputlist: List of tasks to have their response calculated upon
    OBS! could've gone through and made the claim_time_list exclusive before this but felt that it worked and performed as needed so didnt change it.
"""
def calc_response(claim_time_list, outputlist):
    responselist = []
    for task in outputlist: # loop through all tasks in the list
        max_claim = 0          
        for claim in claim_time_list:
            if(int(claim[1]) == int(task[3]) and int(claim[2]) > max_claim): # check if claim is related to this tasks priority, and if bigger then previous max claim time
                max_claim = int(claim[2])
        list_of_preemptions = [preemptive_task for preemptive_task in outputlist if preemptive_task[3] > task[3]] # get all tasks that can preempt the current task via priority checking
        sum_of_preemptions = []
        for preemptive_task in list_of_preemptions:
            sum_of_preemptions.append(math.ceil(int(task[2])/int(preemptive_task[2]))*preemptive_task[1]) # sum up total preemption cost of the tasks that can preempt this task
        total_response_time = 0
        total_response_time += task[1]      # total_time
        total_response_time += max_claim    # max_claim
        for preemption in sum_of_preemptions:
            total_response_time += preemption   # sum of preemptions
        responselist.append([task[0], total_response_time])
    print("\n ASSIGNMENT 3 \n")
    for response in responselist:
        print(str(response[0])+": Response time = "+str(response[1]))

"""
    Setup list for the recursive function, so to contain all necessary data for calculation
    OBS! Could've been done 100 times nicer with oop, but didnt want to break the flow of lists with lists xD
    @input claim_time_list: the list of claims as gathered in the posted_event_init loop with [name, prio, claim_time] for every claim
    @input outputlist: List of tasks to have their response calculated upon
"""
def recursive_setup(claim_time_list, outputlist): #claim list => name, prio, claim_time
    task_list = []
    for task in outputlist: # name, total_time, interval, priority
        task_list.append([task[2], [claim for claim in claim_time_list if str(claim[0]) == str(task[0])], task[3], task[1], 0, task[0]])
        # above is [interval, [claims], prioritys, total_time, response_time, name]
    
    # Remove duplicate claims, only take max value that every task can preempt another task
    exclusive_claim_list = []
    for claim in claim_time_list:
        duplicate = [dupclaim for dupclaim in exclusive_claim_list if dupclaim[1] == claim[1]]
        if len(duplicate) > 0:
            if claim[2] > duplicate[0][2]:
                exclusive_claim_list.append(claim)
                exclusive_claim_list.remove(duplicate[0])
        else:
            exclusive_claim_list.append(claim)

    rec_resp(list(reversed(task_list)), 0, exclusive_claim_list) # reverse to start with highest priority for this calculation
    print("\n ASSIGNMENT 4 \n")
    for line in task_list:
        print(str(line[5])+" : "+str(line[4]) + " STATUS : "+str(line[6]))
    
"""
    The recursive task that calculates the response time
    @input tasklist: The list of tasks to be calculated upon, ex [EXTI1, EXTI2, EXTI3]. The EXTIX objects are lists with data needed for calculation
    @input index: The current task in the tasklist currently being calculated
    @input exclusive_claim_list: The list of claims that have been done with only the maximum claims concearning every task in them

"""
def rec_resp(tasklist, index, exclusive_claim_list):
    if index > (len(tasklist)-1): # list is done 
        return
    new_response = int(tasklist[index][3]) # total_time : wcet
    max_claim = 0   # max claim concearning this task
    for claim in exclusive_claim_list:
        if(int(claim[1]) == int(tasklist[index][2]) and int(claim[2] > max_claim)): # check if priority of claim matches priority of task and if bigger then current max_claim 
            max_claim = int(claim[2])
    new_response += int(max_claim) # add the claim time to new_response variable
    for i in range(0, index): # loop through tasks with higher priority 
        number_of_times_taken = math.ceil(int(tasklist[index][4])/int(tasklist[i][0]))  # calculate number of times it can preempt
        new_response += int(number_of_times_taken) * int(tasklist[i][3])                # add the preemption time to new response
    if (int(new_response) == int(tasklist[index][4]) or int(new_response) > int(tasklist[index][0])): # check if new_response is equal to previous response calculated or bigger then interarrival time
        tasklist[index][4] = int(new_response)                      # set finished response
        tasklist[index].append("OK" if int(new_response) < int(tasklist[index][0]) else "FAIL") # Set status depending on if the task can finish in time
        index += 1 # change to next task in line
        rec_resp(tasklist, index, exclusive_claim_list) # RECURSIVE call
    else:
        tasklist[index][4] = int(new_response) # if not same, update and redo
        rec_resp(tasklist, index, exclusive_claim_list)


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
    global debug
    if debug:
        print("Debug: ktest_setdata on index{}".format(file_index))

    b = KTest.fromfile(file_list[file_index])

    if debug:
        # print('ktest filename : %r' % filename)
        print('Debug: ktest file: %r \n' % file_list[file_index])
        # print('args       : %r' % b.args)
        # print('num objects: %r' % len(b.objects))
    for i, (name, data) in enumerate(b.objects):
        str = trimZeros(data)

        """ If Name is "task", skip it """
        if name.decode('UTF-8') == "task":
            if debug:
                print('Debug: object %4d: name: %r' % (i, name))
                print('Debug: object %4d: size: %r' % (i, len(data)))
            # print(struct.unpack('i', str).repr())
            # task_to_test = struct.unpack('i', str)[0]
            # print("str: ", str)
            # print("str: ", str[0])
            task_to_test = struct.unpack('i', str)[0]
            # task_to_test = int(str[0])
            if debug:
                print("Debug: Task to test:", task_to_test)
        else:
            if debug:
                print('Debug: object %4d: name: %r' % (i, name))
                print('Degug: object %4d: size: %r' % (i, len(data)))
                print(str)
            # if opts.writeInts and len(data) == 4:
            obj_data = struct.unpack('i', str)[0]
            if debug:
                print('Dubug: object %4d: data: %r' %
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
        print("Dubug: Done with setdata")
    return task_to_test


def ktest_iterate():
    """ Get the list of folders in current directory, sort and then grab the
        last one.
    """
    global debug
    global autobuild

    curdir = os.getcwd()
    if debug:
        print("Debug: Current directory {}".format(curdir))

    rustoutputfolder = curdir + "/" + klee_out_folder
    try:
        os.chdir(rustoutputfolder)
    except IOError:
        print(rustoutputfolder + "not found. Need to run\n")
        print("xargo build --example " + example_name + " --features" +
              " klee_mode --target x86_64-unknown-linux-gnu ")
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
                return [x.strip().strip("[]\"").split(' ')
                        for x in line.split(',')]


""" Run xargo for building """


def xargo_run(mode):

    if "klee" in mode:
        xargo_cmd = ("xargo build --release --example " + example_name
                     + " --features "
                     + "klee_mode --target x86_64-unknown-linux-gnu ")
    elif "stm" in mode:
        xargo_cmd = ("xargo build --release --example " + example_name +
                     " --features " +
                     "wcet_bkpt --target thumbv7em-none-eabihf")
    else:
        print("Provide either 'klee' or 'stm' as mode")
        sys.exit(1)

    call(xargo_cmd, shell=True)


""" Stub for running KLEE on the LLVM IR """


def klee_run():
    global debug
    global original_pwd

    PWD = original_pwd

    user_id = subprocess.check_output(['id', '-u']).decode()
    group_id = subprocess.check_output(['id', '-g']).decode()

    bc_file = (glob.glob(PWD + "/" +
                         klee_out_folder +
                         '*.bc', recursive=False))[-1].split('/')[-1].strip(
                             '\'')
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


def gdb_bkpt_read():
    # Read imm field of the current bkpt
    try:
        return int(gdb.execute("x/i $pc", False, True).
                   split("bkpt")[1].strip("\t").strip("\n"), 0)
    except:
        if debug:
            print("Debug: It is not a bkpt so return 4")
        return 4


print("\n\n\nStarting script")

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

""" Tell gdb-dashboard to hide """
# gdb.execute("dashboard -enabled off")
# gdb.execute("dashboard -output /dev/null")

""" Enable the cycle counter """
gdb_cyccnt_enable()
gdb_cyccnt_reset()

""" Save all ktest files into an array """
file_list = ktest_iterate()

""" Get all the tasks to jump to """
task_list = tasklist_get()

if debug:
    print("Debug: file_list {}".format(file_list))
    print("Debug: task_list {}".format(task_list))

""" Split into tasks and priorities """
for x in task_list:
    interarrival.append(x.pop())
    priorities.append(x.pop())
    tasks.append(x.pop())

print("Available tasks:")
for t in tasks:
    print(t)

print("At priorities:")
for t in priorities:
    print(t)

print("At interarrivals:")
for t in interarrival:
    print(t)

""" Subscribe stop_event_ignore to Breakpoint notifications """
gdb.events.stop.connect(stop_event)

"""
    continue until bkpt 3,
    this will pick the next task (through a posted_event_init event)
"""
gdb.execute("continue")


# Home exam, response time analysis
#
# Assignment 1.
# Run the example and study the output.
# you may need to run xargo clean first
#
# It generates `output data`, a list of list, something like:
# Finished all ktest files!
# Claims:
# ['test000002.ktest', 'EXTI1', 0, '1', 'Start']
# ['test000002.ktest', 'EXTI1', 15, 2, 'Enter']
# ['test000002.ktest', 'EXTI1', 19, 3, 'Enter']
# ['test000002.ktest', 'EXTI1', 28, 3, 'Exit'] Claim time: 9
# ['test000002.ktest', 'EXTI1', 29, 2, 'Exit'] Claim time: 14
# ['test000002.ktest', 'EXTI1', 36, '1', 'Finish'] Total time: 36
# ['test000003.ktest', 'EXTI3', 0, '2', 'Start']
# ['test000003.ktest', 'EXTI3', 8, '2', 'Finish'] Total time: 8
# ['test000004.ktest', 'EXTI2', 0, '3', 'Start']
# ['test000004.ktest', 'EXTI2', 11, '3', 'Finish'] Total time: 11
# ['test000005.ktest', 'EXTI1', 0, '1', 'Start']
# ['test000005.ktest', 'EXTI1', 15, 2, 'Enter']
# ['test000005.ktest', 'EXTI1', 19, 3, 'Enter']
# ['test000005.ktest', 'EXTI1', 29, 3, 'Exit'] Claim time: 10
# ['test000005.ktest', 'EXTI1', 30, 2, 'Exit'] Claim time: 15
# ['test000005.ktest', 'EXTI1', 37, '1', 'Finish'] Total time: 37
#
# test000001.ktest is a dummy task and skipped
# ['test000002.ktest', 'EXTI1', 0, 1, 'Start']
# ['test000002.ktest', 'EXTI2', 15, 2, 'Enter']
#
# broken down, the first measurement
# -'test000002.ktest'       the ktest file
# -'EXTI1'                  the task
# -'0'                      the time stamp (start from zero)
# -'1'                      the threshold (priority 1)
# -'Start'                  the 'Start' event
#
# broken down, the second measurement
# -'test000002.ktest'       the ktest file
# -'EXTI1'                  the task
# -'15'                     the time stamp of the 'Enter'
# -'2'                      the threshold (ceiling 2) of X
# -'Enter'                  the 'Enter' event
#
# after 19 cycles we clam Y, raising threshold to 3
# after 28 cycles we exit the Y claim, threshold 3 *before unlock Y*
# after 29 cycles we exit the X claim, threshold 2 *before unlock X*
# and finally we finish at 36 clock cycles
#
# The differences to the hand made measurements are due to details
# of the gdb integration regarding the return behavior.
#
# Verify that you can repeat the experiment.
# The order of tasks/test and cycles may differ but it should look similar.
# Two tests for EXTI1 and one for EXTI2 and one for EXTI3
#
# Try follow what is going on in the test bed.
#
#
# Assignment 2.
#
# The vector
# interarrival = [100, 30, 40]
# should match the arrival time of EXTI1, EXTI2, and EXTI3 respectively
# you may need to change the order depending or your klee/tasks.txt file
# (in the future interarrival and deadlines will be in the RTFM model,
# but for now we introduce them by hand)
#
# Implement function that takes output data and computes the CPU demand
# (total utilization factor) Up of
# http://www.di.unito.it/~bini/publications/2003BinButBut.pdf
#
# For this example it should be
# EXTI1 = 37/100
# EXTI2 = 11/30
# EXTI3 = 8/40
# ------------
# sum   = 0.93666
# So we are inside the total utilization bound <1
#
# Your implementation should be generic though
# Looking up the WCETs from the `output_data`.
# (It may be a good idea to make first pass and extract wcet per task)
#
# The total utilisation bound allows us to discard task sets that are
# obviously illegal (not the case here though)
#
# Assignment 3.
#
# Under SRP response time can be computed by equation 7.22 from
# https://doc.lagout.org/science/0_Computer%20Science/2_Algorithms/Hard%20Real-Time%20Computing%20Systems_%20Predictable%20Scheduling%20Algorithms%20and%20Applications%20%283rd%20ed.%29%20%5BButtazzo%202011-09-15%5D.pdf
#
# In general the response time is computed as.
# Ri =  Ci + Bi + Ii
# Ci the WCET of task i
# Bi the blocking time task i is exposed to
# Ii the interference (preemptions) task is exposed to
#
# where
# Pi the priority of task i
# Ai the interarrival of task i
#
# We assign deadline = interarrival and priorities inverse to deadline
# (rate monotonic assignment, with fixed/static priorities)
#
# Lets start by looking at EXTI2 with the highest priority,
# so no interference (preemption)
# R_EXTI2 = 11 + B_EXTI2 + 0
#
# In general Bi is the max time of any lower priority task
# (EXTI1, EXTI3 in our case)
# holds a resource with a ceiling > Pi (ceiling >= 3 in this case)
# B_EXTI2 = 10 (EXTI1 holding Y for 10 cycles)
#
# Notice 1, single blocking, we can only be blocked ONCE,
# so bound priority inversion
#
# Notice 2, `output_data` does not hold info on WHAT exact resource is held
# merely timestamp information on each Enter/Exit and associated level.
# This is however sufficient for the analysis.
#
# so
# R_EXTI2 = 11 + 10 = 21, well below our 30 cycle margin
#
# Let's look at EXTI3, our mid prio task.
# R_EXTI3 = C_EXTI3 + B_EXTI3 + I_EXTI3
# where I_EXTI3 is the interference (preemptions)
#
# Here we can undertake a simple approach to start out.
# Assuming a deadline equal to our interarrival (40)
# I_EXTI3 is the sum of ALL preemptions until its deadline.
# in this case EXTI2 can preempt us 2 times (40/30 *rounded upwards*)
# I_EXTI3 = 2 * 11
#
# The worst case blocking time is 15
# (caused by the lower prio task EXTI1 holding X)
# R_EXTI3 = 8 + 2 * 11 + 15 = 45, already here we see that
# EXTI2 may miss our deadline (40)
#
# EXTI1 (our lowest prio task)
# R_EXTI1 = C_EXTI1 + B_EXTI1 + I_EXTI1
#
# Here we cannot be blocked (as we have the lowest prio)
# I_EXTI1 is the sum of preemptions from EXTI2 and EXTI3
# our deadline = interarrival is 100
# we are exposed to 100/30 = 4 (rounded upwards) preemptions by EXTI2
# and 100/40 = 3 (rounded upwards) preemptions by EXTI3
#
# I_EXTI1 = 37 + 4 * 11 + 3 * 8 = 105
#
# Ouch, even though we had only a WCET of 37 we might miss our deadline.
# However we might have overestimated the problem.
#
# Implement the algorithm in a generic manner
# Verify that that the results are correct by hand computation (or make an Excel)
#
# Assignment 4.
#
# Looking closer at 7.22 we see that its a recurrent equation.
# Ri(0) indicating the initial value
# Ri(0) = Ci + Bi
# while
# Ri(s) = Ci + Bi + sum ..(Ri(s-1))..
# so Ri(1) is computed from Ri(0) and so forth,
# this requires a recursive or looping implementation.
#
# One can see that as initially setting a "busy period" to Ci+Bi
# and compute a new (longer) "busy period" by taking into account preemptions.
#
# Termination:
# Either Ri(s) = Ri(s-1), we have a fixpoint and have the exact response time
# or we hit Ri(s) > Ai, we have missed our deadline
#
# Your final assignment is to implement the exact method.
#
# Notice, we have not dealt with the case where tasks have equal priorities
# in theory this is not a problem (no special case needed)
#
# However, for exactly analysing the taskset as it would run on the
# real hardware requires some (minor) modifications.
# *Not part of this assignment*
#
# Examination for full score.
# Make a git repo of your solution. (With reasonable comments)
#
# It should be possible to compile and run, and for the example
# Print utilization according to Assignment 2
# Print response times according to Assignment 3
# Print response times according to Assignment 4
#
# It should work with different assignments of the interarrival vector.
# test it also for
# [100, 40, 50]
# [80, 30, 40]
# (Verify that your results are correct by hand computations)
#
# Grading
# For this part 1/3 of the exam 35 points
# Assignment 2, 10 points
# Assignment 3, 10 points
# Assignment 4, 15 points
#
# To make sure the analysis works in the general case
# you can make further examles based on 'resource.rs'
#
# Notice, KLEE analysis does not work on hardware peripherals
# (this is not yet supported), so your new examples must NOT access
# any peripherals.
#
# HINTS
# You may start by cut and paste the output (table) to a file 'x.py'
#
# Implement the analysis in a seprate python file 'x.py'
# (reconstruct the 'outputdata' from the table)
#
# When you have your analysis working,
# integrate it in this script (operating on the real 'outputdata')
#
#
