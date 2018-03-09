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
    gdb.execute("continue")


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


def gdb_call(task):
    # call task
    print("#### call task %s" % task)
    try:
        gdb.execute('call %s' % "stub_" + task + "()")
        print("<<<<<<<<<<<<<<<<< after call >>>>>>>>>>>>>>>>>")

    except gdb.error:
        print("!!!!!!!!!!!!!!!!! after call !!!!!!!!!!!!!!!!!")


def gdb_bkpt_read():
    # Read imm field of the current bkpt
    return int(gdb.execute("x/i $pc", False, True).split("bkpt")[1].strip("\t").strip("\n"), 0)


def gdb_setup():
    # Commands for making GDB scriptable
    print("gbd init")
    gdb.execute("set confirm off")
    gdb.execute("set pagination off")
    # gdb.execute("set verbose off")
    # gdb.execute("set height 0")
    # gdb.execute("set unwindonsignal off")
    # gdb.execute("set unwind-on-terminating-exception off")
    gdb.execute("set unwindonsignal on")
    # gdb.execute("set unwind-on-terminating-exception on")

    gdb.execute("show unwindonsignal")
    gdb.execute("show unwind-on-terminating-exception")


# Event handling
# GDB event, called on breakpoint


def stop_event(evt):
    print("#### stop event %r" % evt)
    gdb.execute("break")
    imm = gdb_bkpt_read()

    print(" imm = {}".format(imm))

    if imm == 0:
        print("-- ordinary breakpoint --")
        # gdb.execute("return")
        # gdb_continue()

    if imm == 1:
        print("Enter")
        # gdb.execute("return")
        # gdb_continue()

    if imm == 2:
        print("Exit")
        # gdb.execute("return")
        # gdb_continue()

    if imm == 3:
        print("Finished")
        # gdb.execute("return")


def exit_handler(event):
    print("event type: exit")
    print("exit code: %d" % (event.exit_code))


# gdb.events.inferior_call_post.connect(exit_handler)


# globals
tasks = ["EXTI1"]
task_nr = 0

print("simple python script started")
gdb_setup()
gdb.events.stop.connect(stop_event)

for t_nr, t_index in enumerate(tasks):
    print("-------------- t_nr {}".format(t_nr))
    gdb_call(tasks[t_nr])
