#ifndef MK61_MARKDOWN_SCROLL_HPP
#define MK61_MARKDOWN_SCROLL_HPP

#include "rust_types.h"

namespace markdown_scroll {

static constexpr u16 VIEWPORT_HEIGHT = 64;
static constexpr u16 FAST_OVERLAP = 8;
static constexpr u16 FAST_DISTANCE = VIEWPORT_HEIGHT - FAST_OVERLAP;

struct Metrics {
  u16 document_height;
  u16 current_top;
  u16 maximum_top;
  u16 previous_anchor;
  u16 next_anchor;
  u16 fast_previous_anchor;
  u16 fast_next_anchor;
  u16 snap_anchor;
};

// Один проход раскладки сообщает все начала визуальных строк и изображений.
// Probe оставляет только соседние и быстрые точки относительно текущего
// пиксельного смещения, поэтому отдельный массив координат не нужен.
class Probe {
 public:
  explicit Probe(u16 current)
      : current(current),
        backward_limit(current > FAST_DISTANCE
            ? (u16) (current - FAST_DISTANCE) : 0),
        forward_limit(current > (u16) (0xFFFFU - FAST_DISTANCE)
            ? 0xFFFFU : (u16) (current + FAST_DISTANCE)),
        previous(0), next(0), fast_previous(0), fast_next(0),
        has_previous(false), has_next(false),
        has_fast_previous(false), has_fast_next(false),
        at_anchor(false) {}

  void note(u16 position) {
    if(position == current) {
      at_anchor = true;
      return;
    }
    if(position < current) {
      if(!has_previous || position > previous) {
        previous = position;
        has_previous = true;
      }
      if(position >= backward_limit &&
         (!has_fast_previous || position < fast_previous)) {
        fast_previous = position;
        has_fast_previous = true;
      }
      return;
    }

    if(!has_next || position < next) {
      next = position;
      has_next = true;
    }
    if(position <= forward_limit &&
       (!has_fast_next || position > fast_next)) {
      fast_next = position;
      has_fast_next = true;
    }
  }

  Metrics finish(u16 document_height) const {
    const u16 maximum = document_height > VIEWPORT_HEIGHT
        ? (u16) (document_height - VIEWPORT_HEIGHT) : 0;
    const u16 top = current > maximum ? maximum : current;
    if(top != current) {
      return {
        document_height, top, maximum,
        top, top, top, top, top
      };
    }

    const u16 previous_target = current == 0
        ? 0 : (has_previous ? previous : 0);
    u16 next_target = current;
    if(current < maximum) {
      next_target = has_next && next < maximum ? next : maximum;
    }

    u16 fast_previous_target = current;
    if(current != 0) {
      if(current <= FAST_DISTANCE) {
        fast_previous_target = 0;
      } else if(has_fast_previous) {
        fast_previous_target = fast_previous;
      } else {
        // Внутри большого изображения или другого длинного элемента может
        // не быть якорей. В таком случае сохраняем перекрытие попиксельно.
        fast_previous_target = backward_limit;
      }
    }

    u16 fast_next_target = current;
    if(current < maximum) {
      if((u16) (maximum - current) <= FAST_DISTANCE) {
        fast_next_target = maximum;
      } else if(has_fast_next && fast_next > current) {
        fast_next_target = fast_next;
      } else {
        // Не перепрыгиваем элемент высотой в целый экран без перекрытия.
        fast_next_target = forward_limit;
      }
    }

    u16 snap_target = current;
    if(!at_anchor) {
      const u16 backward_distance = (u16) (current - previous_target);
      const u16 forward_distance = (u16) (next_target - current);
      snap_target = backward_distance <= forward_distance
          ? previous_target : next_target;
    }

    return {
      document_height, current, maximum,
      previous_target, next_target,
      fast_previous_target, fast_next_target, snap_target
    };
  }

 private:
  u16 current;
  u16 backward_limit;
  u16 forward_limit;
  u16 previous;
  u16 next;
  u16 fast_previous;
  u16 fast_next;
  bool has_previous;
  bool has_next;
  bool has_fast_previous;
  bool has_fast_next;
  bool at_anchor;
};

inline u16 pixel_toward(u16 current, u16 target, u8 step = 1) {
  if(step == 0 || current == target) return current;
  if(current < target) {
    const u16 remaining = (u16) (target - current);
    return remaining <= step ? target : (u16) (current + step);
  }
  const u16 remaining = (u16) (current - target);
  return remaining <= step ? target : (u16) (current - step);
}

// Сдвигает page-major framebuffer на один пиксель вверх и добавляет новую
// нижнюю строку из другого page-major bitmap. Сам Markdown при этом повторно
// раскладывать не нужно.
inline void shift_up_insert_row(
    u8* frame, u16 width, u8 frame_pages,
    const u8* rows, u8 row) {
  if(frame == nullptr || rows == nullptr || width == 0 ||
     frame_pages == 0) return;
  for(u8 page = 0; page + 1U < frame_pages; page++) {
    const usize current = (usize) page * width;
    const usize next = (usize) (page + 1U) * width;
    for(u16 x = 0; x < width; x++) {
      frame[current + x] = (u8) (
          (frame[current + x] >> 1U) |
          (u8) (frame[next + x] << 7U));
    }
  }

  const usize last = (usize) (frame_pages - 1U) * width;
  const usize source = (usize) (row / 8U) * width;
  const u8 source_mask = (u8) (1U << (row & 7U));
  for(u16 x = 0; x < width; x++) {
    frame[last + x] = (u8) (frame[last + x] >> 1U);
    if((rows[source + x] & source_mask) != 0) {
      frame[last + x] |= 0x80U;
    }
  }
}

// Обратный вариант: содержимое движется вниз, новая строка появляется сверху.
inline void shift_down_insert_row(
    u8* frame, u16 width, u8 frame_pages,
    const u8* rows, u8 row) {
  if(frame == nullptr || rows == nullptr || width == 0 ||
     frame_pages == 0) return;
  for(u8 page = (u8) (frame_pages - 1U); page != 0; page--) {
    const usize current = (usize) page * width;
    const usize previous = (usize) (page - 1U) * width;
    for(u16 x = 0; x < width; x++) {
      frame[current + x] = (u8) (
          (u8) (frame[current + x] << 1U) |
          (frame[previous + x] >> 7U));
    }
  }

  const usize source = (usize) (row / 8U) * width;
  const u8 source_mask = (u8) (1U << (row & 7U));
  for(u16 x = 0; x < width; x++) {
    frame[x] = (u8) (frame[x] << 1U);
    if((rows[source + x] & source_mask) != 0) {
      frame[x] |= 0x01U;
    }
  }
}

} // namespace markdown_scroll

#endif
