#ifndef MK61_MSC_DISK_H
#define MK61_MSC_DISK_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* Fixed virtual disk: one LUN, 512-byte FAT sectors. These calls may return
 * BUSY; NOR access and USBDISK.APP execution remain in the foreground loop. */
#define MK61_MSC_FIXED_DISK 1
#define MK61_MSC_SECTOR_SIZE 512U
#define USBD_MSC_STORAGE_ERROR (-1)
#define USBD_MSC_STORAGE_OK 0
#define USBD_MSC_STORAGE_BUSY 1
int8_t MK61_MSC_DiskInit(void);
uint32_t MK61_MSC_DiskBlocks(void);
int8_t MK61_MSC_DiskReady(void);
int8_t MK61_MSC_DiskWriteProtected(void);
int8_t MK61_MSC_DiskRead(uint8_t *buffer, uint32_t lba, uint16_t blocks);
int8_t MK61_MSC_DiskWrite(uint8_t *buffer, uint32_t lba, uint16_t blocks);

#ifdef __cplusplus
}
#endif
#endif
