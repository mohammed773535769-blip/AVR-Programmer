# AVRDUDE GUI Wrapper

A small Windows GUI for programming AVR microcontrollers with AVRDUDE.

## Features

- Read device signature
- Program and verify Intel HEX files
- Read and write fuse bytes
- Detect and refresh COM ports
- Stream AVRDUDE output in the console

## Supported MCUs

- ATtiny85
- ATmega16
- ATmega32
- ATmega328P

## Supported Programmers

- Arduino ISP (`arduino`)
- STK500 v1 (`stk500v1`)
- USBasp (`usbasp`)
- USBtinyISP (`usbtiny`)

## Hardware connections

Arduino Uno ISP wiring:

| Arduino Uno | Target |
|---|---|
| D11 | MOSI |
| D12 | MISO |
| D13 | SCK |
| D10 | RESET |
| GND | GND |
| VCC | VCC |

## Installation

Windows 10 or newer and Python 3 are required. Install the Python dependency:

```bat
python -m pip install -r requirements.txt
```

The bundled `avrdude` folder must contain `avrdude.exe` and `avrdude.conf`.

## Usage

Start the application with:

```bat
python main.py
```

Select the programmer, MCU, COM port and HEX file, then choose an operation.


## License

MIT. See [`LICENSE`](LICENSE).
