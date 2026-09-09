// Build scripts run on the host at compile time; a panic here is the correct
// way to fail the build.
#![allow(clippy::expect_used)]

//! Put `memory.x` on the linker search path and rebuild when it changes.

use std::env;
use std::fs::File;
use std::io::Write;
use std::path::PathBuf;

fn main() {
    let out = PathBuf::from(env::var_os("OUT_DIR").expect("OUT_DIR is set by cargo"));
    File::create(out.join("memory.x"))
        .and_then(|mut f| f.write_all(include_bytes!("memory.x")))
        .expect("write memory.x");
    println!("cargo:rustc-link-search={}", out.display());
    println!("cargo:rerun-if-changed=memory.x");
    println!("cargo:rerun-if-changed=build.rs");
}
