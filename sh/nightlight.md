

crontab
~~~bash
0 * * * * /usr/bin/python3 /<<dir>>/nightlight.py
~~~

nightlight.py
~~~python
from sense_hat import SenseHat
from datetime import datetime 

sh = SenseHat()
nightlight = False
r = [255, 0, 0]  # Red
w = [255, 255, 255]  # White
b = [0, 0, 255]
off = [0, 0, 0]

night_light = [
off, off, off, off, off, off, off, off,
off, w, w, w, w, w, w, off,
off, w, w, w, w, w, w, off,
off, w, w, b, b, w, w, off,
off, w, w, b, b, w, w, off,
off, w, w, w, w, w, w, off,
off, w, w, w, w, w, w, off,
off, off, off, off, off, off, off, off
]



if __name__ == "__main__":
    hr = datetime.now().hour
    lights_on_hrs = [19, 20, 21, 22, 23, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
    sh = SenseHat()
    if hr in lights_on_hrs:
        sh.clear()
        sh.set_pixels(night_light)
    else:
        sh.clear()
~~~
 

~~~
