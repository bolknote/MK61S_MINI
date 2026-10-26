#ifndef MK61_MSC_MEMORY_POLICY_H
#define MK61_MSC_MEMORY_POLICY_H

/* STM32F401 has only 64 KiB of SRAM.  The Arduino STM32 USB configuration
 * defaults MSC_MEDIA_PACKET to 8192 bytes, which makes the BOT handle too
 * large for the guarded F401 heap/stack layout.  A FAT sector is 512 bytes,
 * and the MSC/SCSI implementation already splits longer transfers into
 * MSC_MEDIA_PACKET-sized chunks. */
#if defined(STM32F401xC) || defined(STM32F401xE)
  #define MK61_MSC_COMPACT_MEMORY 1
  #define MK61_MSC_MEDIA_PACKET_BYTES 512U
#else
  #define MK61_MSC_COMPACT_MEMORY 0
  #define MK61_MSC_MEDIA_PACKET_BYTES 8192U
#endif

/* usbd_conf.h may have been included before the project MSC class header. */
#ifdef MSC_MEDIA_PACKET
  #undef MSC_MEDIA_PACKET
#endif
#define MSC_MEDIA_PACKET MK61_MSC_MEDIA_PACKET_BYTES

#endif
