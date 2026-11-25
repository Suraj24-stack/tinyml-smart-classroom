from luma.core.interface.serial import i2c
from luma.oled.device import ssd1306
from luma.core.render import canvas
dev = ssd1306(i2c(port=1, address=0x3C), width=128, height=64)
with canvas(dev) as d:
    d.text((0, 0),  "Smart Classroom", fill="white")
    d.text((0, 20), "OLED OK", fill="white")
input("Press Enter to exit")