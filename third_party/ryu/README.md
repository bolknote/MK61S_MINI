# Ryu binary64 conversion

Source: https://github.com/ulfjack/ryu
Revision: `4c0618b0e44f7ef027ebae05d2cc7812048f7c8f`.

C conversion sources by Ulf Adams, with header includes made relative. Used under the Boost Software
License 1.0 (included); the upstream Apache 2.0 alternative is also included.
The resident compiles the small-table implementation. No allocator is used by
the buffered entry points used by the firmware.
