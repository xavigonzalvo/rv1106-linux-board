// hello-c: smallest C++ check of the cross toolchain. Prints uname, the C++ standard library in use, and a
// little std:: work (string, vector, exceptions) so libstdc++ and libgcc_s are really exercised.
#include <sys/utsname.h>
#include <unistd.h>

#include <cstdio>
#include <iostream>
#include <numeric>
#include <stdexcept>
#include <string>
#include <vector>

int main() {
    utsname u{};
    if (uname(&u) != 0) {
        std::perror("uname");
        return 1;
    }
    std::cout << "Hello from C++ on the RV1106 board\n"
              << "  sysname  " << u.sysname << "\n"
              << "  nodename " << u.nodename << "\n"
              << "  release  " << u.release << "\n"
              << "  version  " << u.version << "\n"
              << "  machine  " << u.machine << "\n";

    std::vector<int> v(10);
    std::iota(v.begin(), v.end(), 1);
    try {
        throw std::runtime_error("sum=" + std::to_string(std::accumulate(v.begin(), v.end(), 0)));
    } catch (const std::exception& e) {
        std::cout << "  exception ok: " << e.what() << "\n";
    }
#if defined(__UCLIBC__)
    std::cout << "  libc     uClibc " << __UCLIBC_MAJOR__ << "." << __UCLIBC_MINOR__ << "."
              << __UCLIBC_SUBLEVEL__ << "\n";
#endif
    std::cout << "  gcc      " << __VERSION__ << ", C++ " << __cplusplus << "\n"
              << "  pid      " << getpid() << "\n";
    return 0;
}
