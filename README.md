# axi

Python 3 library for working with the [AxiDraw v3](http://www.axidraw.com/) pen plotter.

> **Note:** This is a fork of the original [axi](https://github.com/fogleman/axi) library by [Michael Fogleman](https://github.com/fogleman). Full credit for the original design and implementation goes to him. This fork adds Python 3 support, bug fixes, and image drawing utilities.

### What's New (Python 3 Fork)

- **Python 3 support** — fully migrated from Python 2 (removed `__future__` imports, fixed `print`, `xrange`, `filter`/`zip`, integer division, etc.)
- **Binary image to plotter** — read any black-on-white PNG and draw it using contour extraction (`scikit-image`)
- **Serial stability** — retry logic and increased timeout for USB connection drops
- **Bug fixes** — pen up/down command correction, `ZeroDivisionError` fix in progress bar for empty drawings

### Features

- control AxiDraw v3 directly from Python with a simple API
- convenient command-line utility
- constant acceleration (trapezoidal velocity) motion planning
- path drawing order optimization
- draw from binary PNG images (contour extraction + greedy path sorting)
- drawing transformations
  - translate, scale, rotate
  - scale and/or rotate to fit page
  - move to origin or center of page
- preview drawing (render to png)
- [turtle graphics](https://en.wikipedia.org/wiki/Turtle_graphics)

### Command Line Utility

Once installed, you can run the `axi` command-line utility. Here are the supported commands:

```
axi on         # enable the motors
axi off        # disable the motors
axi up         # move the pen up
axi down       # move the pen down
axi zero       # set current position as (0, 0)
axi home       # return to the (0, 0) position
axi move DX DY # move (DX, DY) inches, relative
axi goto X Y   # move to the (X, Y) absolute position
```

### TODO

- primitives
  - circles, arcs, beziers
- svg support

### Installation

Requires **Python 3.7+**.

```bash
git clone https://github.com/aiarcade/axi.git
cd axi
python3 -m venv venv
source venv/bin/activate
pip install -e .
pip install Pillow scikit-image   # for image drawing support
```

### Drawing from a Binary Image

Generate a line-drawing PNG and plot it:

```bash
python create_image.py    # creates face_drawing.png
python sample_test.py     # reads the PNG and draws on the plotter
```

`sample_test.py` reads any black-on-white PNG, extracts contours using `scikit-image`, simplifies paths, and draws them on the AxiDraw using direct device calls.

### Quick Test

A minimal test to verify your plotter connection (draws a 1-inch square):

```bash
python simple_test.py
```

### Example

Use the turtle to draw a dragon curve, filling a standard US letter page.

```python
import axi

def main(iteration):
    turtle = axi.Turtle()
    for i in range(1, 2 ** iteration):
        turtle.forward(1)
        if (((i & -i) << 1) & i) != 0:
            turtle.circle(-1, 90, 36)
        else:
            turtle.circle(1, 90, 36)
    drawing = turtle.drawing.rotate_and_scale_to_fit(11, 8.5, step=90)
    axi.draw(drawing)

if __name__ == '__main__':
    main(12)
```

### Credits

- **Original library:** [Michael Fogleman](https://github.com/fogleman) — [fogleman/axi](https://github.com/fogleman/axi)
- **Python 3 fork & enhancements:** [aiarcade](https://github.com/aiarcade)

### License

See [LICENSE.md](LICENSE.md) for details.
