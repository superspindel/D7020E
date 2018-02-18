//! Minimal example with zero tasks
//#![deny(unsafe_code)]
// IMPORTANT always include this feature gate
#![feature(proc_macro)]
#![no_std]

extern crate cortex_m_rtfm as rtfm;
// IMPORTANT always do this rename
extern crate stm32f103xx;

#[macro_use]
extern crate klee;
use klee::{k_abort, k_assert};

// import the procedural macro
use rtfm::app;

app! {
    // this is the path to the device crate
    device: stm32f103xx,
}

fn t(x: &mut i32) -> i32 {
    let mut y = 0;
    if *x < 10 {
        for _ in 0..*x {
            y += 1;
            k_visit!()
        }
    }
    y
}

pub fn t2() {
    let mut x = 0;
    let x: &mut i32 = &mut x;
    k_symbol!(x, "x");

    let mut y = 0;
    let y: &mut i32 = &mut y;
    k_symbol!(y, "y");

    t(x) + t(y);
}

#[inline(never)]
fn init(_p: init::Peripherals) {
    t2();
}
