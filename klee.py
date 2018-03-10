#!/usr/bin/env python
import gdb
import os
import sys
import struct
from subprocess import call
import subprocess
import glob


# gdb helper functions
def gdb_continue():
    # gdb.execute("continue")
    gdb.execute("signal 0")


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


def gdb_set_pc(task):
    gdb.execute("set $pc = stub_{}()".format(task))


def gdb_call(task):
    # call task
    print("#### call task %s" % task)
    gdb.execute('call %s' % "stub_" + task + "()")


def gdb_bkpt_read():
    # Read imm field of the current bkpt
    return int(gdb.execute("x/i $pc", False, True).split("bkpt")[1].strip("\t").strip("\n"), 0)


def gdb_setup():
    # Commands for making GDB scriptable
    print("gbd init")
    gdb.execute("set confirm off")
    gdb.execute("set pagination off")
    gdb.execute("set verbose off")
    gdb.execute("set height 0")
    # gdb.execute("set unwindonsignal on")
    # gdb.execute("set unwindonsignal off")
    # gdb.execute("set unwind-on-terminating-exception on")
    # gdb.execute("set unwind-on-terminating-exception off")

    gdb.execute("show unwindonsignal")
    gdb.execute("show unwind-on-terminating-exception")

# set unwindonsignal on
# will unwind the stack on a signal error, we don't want that


# Event handling

# Ugly hack to avoid race condtitons in the python gdb API

class Executor:
    def __init__(self, cmd):
        self.__cmd = cmd

    def __call__(self):
        gdb.execute(self.__cmd)

# GDB event, called on breakpoint


def stop_event(evt):
    global task_nr
    # print("#### stop event %r" % evt)
    imm = gdb_bkpt_read()

    print(" imm = {}".format(imm))

    if imm == 0:
        print("-- ordinary breakpoint --")
        sys.exit(1)

    if imm == 1:
        print(">>>>>>>>>>>>> Enter")

        gdb.post_event(Executor("continue"))

    if imm == 2:
        print("<<<<<<<<<<<<< Exit")
        gdb.post_event(Executor("continue"))

    if imm == 3:
        print("------------- Finished")
        task_nr = task_nr + 1
        # gdb.execute("si")
        gdb.execute("return")

        gdb.post_event(posted_event_init)


def posted_event_init():
    print("")
    print("------------- posted_event_init ")
    global tasks
    global task_nr
    print("------------- task nr {}".format(task_nr))

    if task_nr >= len(tasks):
        print("------------- tasks done")
        gdb.events.stop.disconnect(stop_event)
        return
        # gdb.execute("quit")
    else:
        try:
            gdb_call(tasks[task_nr])
            print("!!!!!!!!!!!!!!!!!!!!!! ERROR !!!!!!!!!!!!!!!!!!!!!!!!")
            sys.exit(1)
        except:
            print("------------- call except")


# globals
# tasks = ["EXTI2", "EXTI3", "EXTI3"]
tasks = ["EXTI3", "EXTI2", "EXTI1"]
task_nr = 0

print("simple python script started")
gdb_setup()
gdb.events.stop.connect(stop_event)
gdb.post_event(posted_event_init)
