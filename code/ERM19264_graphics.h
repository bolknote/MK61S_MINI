 /*!
	@file ERM19264_graphics.h
	@brief ERM19264 LCD driven by UC1609 controller, header file
		for the graphics  based functions.
	@details Project Name: ERM19264_UC1609
		URL: <https://github.com/gavinlyonsrepo/ERM19264_UC1609>
	@author  Gavin Lyons
*/

#ifndef _ERM19264_GRAPHICS_H
#define _ERM19264_GRAPHICS_H

#if ARDUINO >= 100
 #include "Arduino.h"
 #include "Print.h"
#else
 #include "WProgram.h"
#endif

#define ERM19264_swap(a, b) { int16_t t = a; a = b; b = t; }

/*! LCD rotate modes in degrees, Note this is separate from LCD command method for rotation. */
enum  LCD_rotate_e : uint8_t
{
	LCD_Degrees_0 = 0, /**< No rotation 0 degrees*/
	LCD_Degrees_90,    /**< Rotation 90 degrees*/
	LCD_Degrees_180,   /**< Rotation 180 degrees*/
	LCD_Degrees_270   /**< Rotation 270 degrees*/
};

/*! LCD Enum to define return codes from some text and bitmap functions  */
enum LCD_Return_Codes_e : uint8_t
{
	LCD_Success = 0,                /**< Success!  */
	LCD_CharScreenBounds = 3,       /**< Text Character is out of Screen bounds, Check x and y*/
	LCD_CharFontASCIIRange = 4,     /**< Text Character is outside of chosen Fonts ASCII range, Check the selected Fonts ASCII range.*/
	LCD_CharArrayNullptr = 5,       /**< Text Character Array is an invalid pointer object */
	LCD_BitmapNullptr = 7,          /**< The Bitmap data array is an invalid pointer object */
	LCD_BitmapScreenBounds = 8,     /**< The bitmap starting point is outside screen bounds check x and y */
	LCD_BitmapLargerThanScreen = 9, /**< The Bitmap is larger than screen , check  w and h*/
	LCD_BitmapVerticalSize = 10,    /**< A vertical  Bitmap's height must be divisible by 8. */
	LCD_BitmapHorizontalSize = 11,  /**< A horizontal Bitmap's width  must be divisible by 8  */
	LCD_SPIBusBusy = 12,            /**< The shared SPI bus could not be acquired safely. */
};

/*! @brief Graphics class to hold graphic related functions */
class ERM19264_graphics : public Print {

 public:

	ERM19264_graphics(int16_t w, int16_t h);

	// This is defined by the subclass:
	virtual void drawPixel(int16_t x, int16_t y, uint8_t color) = 0;

	// Shape related
	void drawLine(int16_t x0, int16_t y0, int16_t x1, int16_t y1, uint8_t color);
	void drawFastVLine(int16_t x, int16_t y, int16_t h, uint8_t color);
	void drawFastHLine(int16_t x, int16_t y, int16_t w, uint8_t color);
	void drawRect(int16_t x, int16_t y, int16_t w, int16_t h, uint8_t color);
	void fillRect(int16_t x, int16_t y, int16_t w, int16_t h, uint8_t color);
	void fillScreen(uint8_t color);

	void	drawCircle(int16_t x0, int16_t y0, int16_t r, uint8_t color);
	void	drawCircleHelper(int16_t x0, int16_t y0, int16_t r, uint8_t cornername,
			uint8_t color);
	void	fillCircle(int16_t x0, int16_t y0, int16_t r, uint8_t color);
	void	fillCircleHelper(int16_t x0, int16_t y0, int16_t r, uint8_t cornername,
			int16_t delta, uint8_t color);
	void	drawTriangle(int16_t x0, int16_t y0, int16_t x1, int16_t y1,
			int16_t x2, int16_t y2, uint8_t color);
	void	fillTriangle(int16_t x0, int16_t y0, int16_t x1, int16_t y1,
			int16_t x2, int16_t y2, uint8_t color);
	void	drawRoundRect(int16_t x0, int16_t y0, int16_t w, int16_t h,
			int16_t radius, uint8_t color);
	void	fillRoundRect(int16_t x0, int16_t y0, int16_t w, int16_t h,
			int16_t radius, uint8_t color);
			
	// Bitmap related
	LCD_Return_Codes_e drawBitmap(int16_t x, int16_t y, const uint8_t *bitmap,
			int16_t w, int16_t h, uint8_t color, uint8_t bg);
	void	setDrawBitmapAddr(bool mode);

	// Text related
	void	setCursor(int16_t x, int16_t y);
	void	setTextColor(uint8_t c);
	void	setTextColor(uint8_t c, uint8_t bg);
	void	setTextSize(uint8_t s);
	void	setTextWrap(bool w);
	LCD_Return_Codes_e drawChar(int16_t x, int16_t y, unsigned char c, uint8_t color, uint8_t bg, uint8_t s);
	LCD_Return_Codes_e drawText(uint8_t x, uint8_t y, char *pTxt, uint8_t c, uint8_t bg, uint8_t s);

#if ARDUINO >= 100
	virtual size_t write(uint8_t);
#else
	virtual void   write(uint8_t);
#endif

	// Screen related
	int16_t height(void) const;
	int16_t width(void) const;
	void setRotation(LCD_rotate_e );
	LCD_rotate_e getRotation(void);

 protected:

	const int16_t WIDTH;  /**< This is the 'raw' display w - never changes */
	const int16_t HEIGHT;  /**< This is the 'raw' display h - never changes*/
	int16_t _width;  /**< Display w as modified by current rotation*/
	int16_t _height;  /**< Display h as modified by current rotation*/
	int16_t _cursorX; /**< Current X co-ord cursor position */
	int16_t _cursorY;  /**< Current Y co-ord cursor position */
	LCD_rotate_e LCD_rotate = LCD_Degrees_0; /**< Enum to hold rotation */

	uint8_t _textColor= 0x00;  /**< Text foreground color */
	uint8_t _textBgColor= 0x01;   /**< Text background color */
	uint8_t   _textSize= 1; /**< Integer scale of the resident 5x8 font */
	bool _textWrap;                       /**< If set, 'Wrap' text at right edge of display*/

	bool drawBitmapAddr; /**< data addressing mode for method drawBitmap, True-vertical , false-horizontal */
private:
	static constexpr uint8_t FONT_WIDTH = 5;
	static constexpr uint8_t FONT_HEIGHT = 8;
	static constexpr uint8_t FONT_LENGTH = 128;

};

#endif
