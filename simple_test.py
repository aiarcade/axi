"""
Simple direct plotter test - draw a small 1-inch square.
Uses axi.Device() directly, like the original working sample_test.py.
"""
import axi

def main():
    d = axi.Device()
    print('Connected to AxiDraw')

    # Make sure motors are on
    d.enable_motors()

    # Start with pen up, move to start position
    d.pen_up()
    print('Pen up')

    # Move to starting position (1, 1)
    d.goto(1, 1)
    print('Moved to start (1, 1)')

    # Put pen down
    d.pen_down()
    print('Pen down')

    # Draw a small 1-inch square
    d.move(1, 0)    # right
    print('  -> right')
    d.move(0, 1)    # down
    print('  -> down')
    d.move(-1, 0)   # left
    print('  -> left')
    d.move(0, -1)   # up (back to start)
    print('  -> up')

    # Pen up and go home
    d.pen_up()
    print('Pen up')

    d.goto(0, 0)
    print('Homed')

    d.disable_motors()
    print('Done!')

if __name__ == '__main__':
    main()
