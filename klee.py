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
    gdb.execute('call %s' % "stub_" + task + "()")
    print("<<<<<<<<<<<<<<<<< after call >>>>>>>>>>>>>>>>>")


def gdb_setup():
    # Commands for making GDB scriptable
    print("gbd init")
    gdb.execute("set confirm off")
    gdb.execute("set pagination off")
    gdb.execute("set verbose off")
    gdb.execute("set height 0")
    # gdb.execute("set unwindonsignal off")
    gdb.execute("set unwindonsignal on")

# Event handling

# GDB event, called on breakpoint


def stop_event(evt):
    print("#### stop event %r" % evt)

    try:
        ceiling = int(gdb.parse_and_eval("ceiling").
                      cast(gdb.lookup_type('u8')))
        print("ceiling %r" % ceiling)
        gdb_continue()

    except gdb.error:
        print("#### return")
        gdb.post_event(next)

        next()


def next():
    global task_nr
    global tasks

    task_nr = task_nr + 1

    if task_nr == len(tasks):
        print("------------ all done ---------")
        return
    print("-------------- start {}-------------".format(task_nr))
    gdb_call(tasks[task_nr - 1])
    print("-------------- finshed {}-------------".format(task_nr))
    next()

# def next_event(next):
#     global task_nr
#     global tasks

#     if task_nr == tasks.lenght():
#         print("vvvvvvvvvvvvvvvvv")
#         return
#     print("-------------- start {}-------------".format(task_nr))
#     gdb_call(tasks[t_nr])

#     gdb.post_event(next)



# globals
tasks = ["EXTI2", "EXTI3", "EXTI1"]
task_nr = 0

print("simple python script started")
gdb_setup()
gdb.events.stop.connect(stop_event)
next()
# gdb.events.next.connect(next_event)
# gdb.post_event(next)


# for t_nr, t_index in enumerate(tasks):
#     busy = True
#     sad = False

#     try:
#         gdb_call(tasks[t_nr])
#     except:
#         print("############ call failed #############")
#         while busy:
#             gdb_continue()
#             while sad:
#                 pass
