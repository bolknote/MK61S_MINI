// name, diagnostic name, allowed arenas, persistent arenas,
// opportunistic-cache arenas, synchronously-evictable arenas,
// volatile snapshot schema
//
// Include with MK61_SHARED_MEMORY_OWNER defined. This file deliberately has no
// include guard: it generates the enum, packed policy table and name table.
MK61_SHARED_MEMORY_OWNER(NONE, "none", 0, 0, 0, 0, 0)
MK61_SHARED_MEMORY_OWNER(FOCAL, "focal", arena_mask(Arena::WORKSPACE),
                         arena_mask(Arena::WORKSPACE), 0, 0,
                         snapshot_schema::FOCAL_RUNTIME)
MK61_SHARED_MEMORY_OWNER(TINYBASIC, "basic", arena_mask(Arena::WORKSPACE),
                         arena_mask(Arena::WORKSPACE), 0, 0,
                         snapshot_schema::TINYBASIC_RUNTIME)
MK61_SHARED_MEMORY_OWNER(
    IMAGE_VIEWER, "image", (arena_mask(Arena::WORKSPACE) |
                            arena_mask(Arena::SCRATCH)), 0, 0, 0, 0)
MK61_SHARED_MEMORY_OWNER(
    MARKDOWN_VIEWER, "markdown", (arena_mask(Arena::WORKSPACE) |
                                  arena_mask(Arena::SCRATCH)), 0, 0, 0, 0)
MK61_SHARED_MEMORY_OWNER(CHIP8, "chip8", arena_mask(Arena::WORKSPACE),
                         0, 0, 0, 0)
MK61_SHARED_MEMORY_OWNER(USB_DISK, "usb-disk", arena_mask(Arena::WORKSPACE),
                         0, 0, 0, 0)
MK61_SHARED_MEMORY_OWNER(
    TERMINAL_TRANSFER, "terminal",
    (arena_mask(Arena::WORKSPACE) | arena_mask(Arena::SCRATCH)),
    arena_mask(Arena::WORKSPACE), 0, 0, 0)
MK61_SHARED_MEMORY_OWNER(CORE_TABLES, "core-tables",
                         arena_mask(Arena::WORKSPACE), 0,
                         arena_mask(Arena::WORKSPACE),
                         arena_mask(Arena::WORKSPACE), 0)
MK61_SHARED_MEMORY_OWNER(EXPLORER_VIEW, "explorer",
                         arena_mask(Arena::SCRATCH), 0, 0, 0, 0)
MK61_SHARED_MEMORY_OWNER(M61_FORMAT, "m61-format",
                         arena_mask(Arena::SCRATCH), 0, 0, 0, 0)
MK61_SHARED_MEMORY_OWNER(PROGRAM_STORE_RENAME, "store-rename",
                         arena_mask(Arena::SCRATCH), 0, 0, 0, 0)
MK61_SHARED_MEMORY_OWNER(PROGRAM_STORE_READ_RANGE, "store-read",
                         arena_mask(Arena::SCRATCH), 0, 0, 0, 0)
MK61_SHARED_MEMORY_OWNER(
    PROGRAM_STORE_COMPRESSION, "zx0",
    (arena_mask(Arena::WORKSPACE) | arena_mask(Arena::SCRATCH) |
     arena_mask(Arena::BULK)),
    0, arena_mask(Arena::WORKSPACE), 0, 0)
MK61_SHARED_MEMORY_OWNER(VFAT_COMMIT, "vfat-commit",
                         arena_mask(Arena::SCRATCH), 0, 0, 0, 0)
MK61_SHARED_MEMORY_OWNER(
    USB_CACHE, "usb-cache",
    (arena_mask(Arena::SCRATCH) | arena_mask(Arena::BULK)), 0, 0, 0, 0)
MK61_SHARED_MEMORY_OWNER(DISPLAY_FONT, "font", arena_mask(Arena::BULK),
                         0, 0, 0, 0)
MK61_SHARED_MEMORY_OWNER(
    WORKSPACE_SWAP, "workspace-swap",
    (arena_mask(Arena::SCRATCH) | arena_mask(Arena::BULK)), 0,
    arena_mask(Arena::BULK), arena_mask(Arena::BULK), 0)
