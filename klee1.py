#!/usr/bin/env python
import gdb
import os
import sys
import struct
from subprocess import call
import subprocess
import glob


def posted_event_init():
    print("--------------- Entering posted_event_init")


# class MainBP(gdb.Breakpoint):

#     def stop(self):
#         print("zzzzzzzzzzzzzzz")
#         print("Breakpoint location: %s" % self.location)
#         gdb.execute('c')


def stop_event(evt):
        print("zzzzzzzzzzzzzzz")
        print("Stop event: %s" % evt)
        #gdb.execute('c')


print("Python script started")
gdb.execute("set confirm off")
gdb.execute("set pagination off")
gdb.execute("set verbose off")
gdb.execute("set height 0")

gdb.events.stop.connect(stop_event)
gdb.execute('call stub_EXTI1()')


# Hooking the prompt:
def prompt(current):
    # print("current %r" % current)
    # print("#### prompt")
    gdb.prompt_hook = current