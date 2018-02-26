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
use klee::k_assert;

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
    let mut j = 0;
    for _ in 0..100 {
        j += 1;
    }
    k_assert(j == 100);
    k_assert(j == 101);
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
// LLVM KLEE is a tool for symbolic execution operating on LLVM bit code (`*.bc` files)
//
// You can generate a LLVM BC from a Rust RTFM application by
//
// 1> rustup override set nightly-2018-01-10
//
// 2> xargo build --example panic1 --features klee_mode --target x86_64-unknown-linux-gnu
//
// 1) We need a slightly older version of Rust with a LLVM 4 backend to run KLEE
//    `rustup override` will stick the directory to a set tool-chain (run once)
//
// 2) As LLVM runs on our host we generate the `.bc` with x86 as target
//
// Start a docker with pre-installed KLEE tools
//
// 3>  docker run --rm --user $(id -u):$(id -g) -v $PWD/target/x86_64-unknown-linux-gnu/debug/examples:/mnt -w /mnt -it afoht/llvm-klee-4 /bin/bash
//
// 3) This will start the docker with the right privileges and mount the directory
//    where the example `.bc` file(s) are stored (shared/overlaid with the host file system).
//
// You can now let KLEE run on the `.bc` file.
//
// 4> klee panic1*.bc
// ...
// KLEE: WARNING: undefined reference to function: WWDG
// KLEE: WARNING: executable has module level assembly (ignoring)
// KLEE: ERROR: /home/pln/klee/cortex-m-rtfm/klee/src/lib.rs:48: abort failure
// KLEE: NOTE: now ignoring this error at this location
//
// KLEE: done: total instructions = 66549
// KLEE: done: completed paths = 2
// KLEE: done: generated tests = 2
//
// Here the loop is executed by the virtual machine and the `k_assert`s checked.
// As a expected the second `k_assert` will fail (as j is 100 not 101).
//
// The latest experiment is linked under the `klee-last` directory.
//
// 5> ls klee-last
// ...
// test000002.abort.err
// ...
// 6> cat klee-last/test000002.abort.err
// ...
// #100000921 in EXTI1 () at /home/pln/klee/cortex-m-rtfm/examples/panic1.rs:19
// ...
// 6) the file gives you a stack trace leading up to the error,
//    we are just concerned with the line number in the `panic1.rs` file.
//
// So the lesson learned here is just that KLEE can execute our code
// and we can get stack traces for failing assertions, nothing more.
//
// Show to the lab assistant that you can replicate the above, and explain
// the process and result.
