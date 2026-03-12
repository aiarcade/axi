"""
calibrate_steps.py — Determine the correct STEPS_PER_INCH for your plotter.

Draws a horizontal and vertical line that the code thinks is 4 inches each.
Measure the actual length with a ruler and enter it to compute the correction.
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import axi

def main():
    d = axi.Device()
    d.enable_motors()
    d.zero_position()
    d.pen_up()
    time.sleep(0.5)

    target = 4.0  # inches (what the code thinks)

    # Draw horizontal line (4 inches in X)
    print(f'Drawing a horizontal line — code thinks it is {target}" long...')
    d.pen_down()
    time.sleep(0.2)
    d.run_path([(0, 0), (target, 0)])
    d.pen_up()
    time.sleep(0.3)

    # Return to origin
    d.run_path([(target, 0), (0, 0)], jog=True)
    time.sleep(0.3)

    # Draw vertical line (4 inches in Y)
    print(f'Drawing a vertical line — code thinks it is {target}" long...')
    d.pen_down()
    time.sleep(0.2)
    d.run_path([(0, 0), (0, target)])
    d.pen_up()
    time.sleep(0.3)

    # Return to origin
    d.run_path([(0, target), (0, 0)], jog=True)
    d.disable_motors()

    print()
    print('Now measure both lines with a ruler (in inches or cm).')
    unit = input('Are you measuring in inches or cm? [cm/inches]: ').strip().lower()
    h = float(input('Horizontal line actual length: '))
    v = float(input('Vertical line actual length: '))

    if unit.startswith('c'):
        h /= 2.54
        v /= 2.54

    current_spi = d.steps_per_unit
    h_spi = current_spi * target / h
    v_spi = current_spi * target / v
    avg_spi = (h_spi + v_spi) / 2

    print()
    print(f'Current STEPS_PER_INCH : {current_spi}')
    print(f'Measured H: {h:.2f}"  → STEPS_PER_INCH = {h_spi:.0f}')
    print(f'Measured V: {v:.2f}"  → STEPS_PER_INCH = {v_spi:.0f}')
    print(f'Average STEPS_PER_INCH : {avg_spi:.0f}')
    print()
    print(f'To fix, update STEPS_PER_INCH in axi/device.py to {avg_spi:.0f}')

if __name__ == '__main__':
    main()
