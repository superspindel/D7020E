//! Minimal example with zero tasks
//#![deny(unsafe_code)]
// IMPORTANT always include this feature gate
#![feature(proc_macro)]
#![feature(used)]
#![no_std]

extern crate cortex_m_rtfm as rtfm;
// IMPORTANT always do this rename
extern crate stm32f413;

#[macro_use]
extern crate klee;
use klee::{k_abort, k_assert};

// import the procedural macro
use rtfm::{app, Resource, Threshold};

app! {
    // this is the path to the device crate
    device: stm32f413,

    tasks: {
        EXTI1: {
            path: exti1,
            priority: 1,
        },
    },
}

fn exti1() {
    let mut j: u8 = 0; // unsigned 8 bit integer
    k_symbol!(&mut j, "j");
    if j > 10 {
        k_abort();
    } else {
        k_assert(1 == 0);
    }
}
// The `init` function
//
// This function runs as an atomic section before any tasks
// are allowed to start
#[inline(never)]
#[allow(dead_code)]
fn init(_p: init::Peripherals) {}

// The idle loop.
//
// This runs after `init` and has a priority of 0. All tasks can preempt this
// function. This function can never return so it must contain some sort of
// endless loop.
#[inline(never)]
fn idle() -> ! {
    loop {}
}

// Assignments
//
// The real power of KLEE is the ability to symbolic execution.
// We mark the mutable variable `j` as being symbolic (unknown).
//
// > xargo build --example panic2 --features klee_mode --target x86_64-unknown-linux-gnu
//
// You can now let KLEE run on the `.bc` file.
//
// > klee panic1*.bc
// ...
// KLEE: ERROR: /home/pln/klee/cortex-m-rtfm/klee/src/lib.rs:48: abort failure
// KLEE: NOTE: now ignoring this error at this location
// KLEE: ERROR: /home/pln/klee/cortex-m-rtfm/klee/src/lib.rs:48: abort failure
// KLEE: NOTE: now ignoring this error at this location

// KLEE: done: total instructions = 193
// KLEE: done: completed paths = 3
// KLEE: done: generated tests = 3
//
// > ls klee-last/*err
// klee-last/test000002.abort.err  klee-last/test000003.abort.err
//
// > cat klee-last/test000002.abort.err
//  ... /home/pln/klee/cortex-m-rtfm/examples/panic2.rs:35
//
// > cat klee-last/test000003.abort.err
//  ... /home/pln/klee/cortex-m-rtfm/examples/panic2.rs:37
//
// (logically a failing `k_assert` amounts to a `k_abort`)
//
// KLEE also provides us with "counter examples" for the failing assertions.
//
// We can use the `ktest-tool` (python script) to inspect those.
//
// > ktest-tool klee-last/test000002.ktest
// ktest file : 'klee-last/test000002.ktest'
// args       : ['panic2-46c7df2ab3607698.bc']
// num objects: 2
// object    0: name: b'task'
// object    0: size: 4
// object    0: data: b'\x00\x00\x00\x00'
// object    1: name: b'j'
// object    1: size: 1
// object    1: data: b'\xff'
//
// task here amounts to the task we are inspecting (in this case only one...)
// 'j' has the value 0xff (255 as integer), triggering the `then` branch
//
// and
// > ktest-tool klee-last/test000003.ktest
// ...
// object    1: name: b'j'
// object    1: size: 1
// object    1: data: b'\x00'
//
// here 'j' has the value 0x00 (0 as integer), triggering the `else` branch
//
// How, can KLEE figure out concrete values for the symbolic variable `j`?
// Well, it tracks the data dependencies and condititonals along feasible execution paths
// of the program (task EXTI1 in our case). And when encountering a `k_abort`
// it passes the collected (path) condition to an SMT solver.
// The solver returns with a concrete assigmnent for a `k_abort` if possible.
// This can be seen as a reachabilty proof or (equivalently) as a counter example
// to an `k_assert`.
//
// Show to the lab assistant that you can replicate the above, and explain
// the process and result.
