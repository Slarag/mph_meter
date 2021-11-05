#!/usr/bin/env python3

__title__ = 'mph Meter Configurator'
__description__ = 'Tool for configuring mph Meter written by Michael Fiederer'
__author__ = 'Michael Fiederer'
__version__ = '2.0'
__date__ = '2020-04-10'

"""
Required modules:
-pyserial (serial)

Required Software:
-None

Changelog:
    -1.0:
        -initial version
    -2.0:
        -Splitted application into Model & View
        -Prevent user from entering invalid charactes by adding validation to entries
        -Pressing Set for empty Entry fields no longer causes an exception
        -Added "Restore Defaults" button
        -Added "Flash FW" Button by wrapping avrdude
        -Increased possibly SW debounce time from 999ms to 999.999ms
        -ToDo:
            -Add CLI
            
"""

#using tkinter as GUI toolkit
import tkinter as tk
import tkinter.messagebox as messagebox
import tkinter.ttk as ttk

#Used for command line interface (CLI)
import argparse

#Used for running avrdude to update firmware
import subprocess
import os.path

#Using pyserial for serial port communication
import serial
import serial.tools.list_ports as serialports

#Default values to programm into mph Meter when Restore Defaults button is clicked
DEFAULTS = {
    'muempp_µm': 43000,
    'debounce_ms': 0,
    'vwarn_v': 7.5,
    }


#Exceptions
class ReplyError(Exception):
    """Raised when an invalid reply from mph Meter received"""
    def __init__(self, text=None, value=None):
        super().__init__()
        self.text = text
        self.value = value

class BoundaryError(Exception):
    """Raised when trying to set a value of the mph Meter that is out of boundaries"""
    def __init__(self, text, value=None):
        super().__init__()
        self.text = text
        self.value = value
    def __str__(self):
        return self.text + ' ({})'.format(repr(self.value))

class NotConnectedError(Exception):
    """Raised when an operation is performed on mph Meter, before it was connected"""
    pass

class LostConnectionError(Exception):
    """Raised when connection to mph Meter is broken"""
    pass


#Model
class MphMeter():
    """Abstraction model / implementation of mph Meter"""
    
    def __init__(self):
        self._serial = serial.Serial(baudrate=9600,timeout=0.9)

    def _runcmd(self, cmd):
        """Send command over serial port and return reply"""
        
        if not self._serial.is_open:
            raise NotConnectedError
        
        try:
            self._serial.write((cmd + '\n').encode('ascii'))
            self._serial.flush()
            reply = self._serial.read_until(b'\n').decode('ascii', errors='ignore').strip()
        except serial.SerialException:
            self._serial.close()
            raise LostConnectionError
            
        return reply

    def _setvalue(self, cmd, value, name, b_low, b_high, unit=''):
        """Programm a value into mph Meter. Eveluate boundaries, evaluate reply from mph Meter and show success/fail dialogs accordingly"""
        
        if not self._serial.is_open:
            raise NotConnectedError
        
        if not b_low <= value <= b_high:
            raise BoundaryError('{name} must be between {b_low}{unit} and {b_high}{unit}!'.format(name=name, b_low=b_low, b_high=b_high, unit=unit), value)
        
        reply = self._runcmd(cmd)
        
        if reply == 'ERR':
            raise ReplyError('Error setting {name} value'.format(name=name))
        elif reply == '':
            raise ReplyError('No reply received')
        elif reply!= 'OK':
            raise ReplyError('Incorrect reply received: {}'.format(repr(reply)))

    def connect(self, port):
        """Establish connection to physical mph Meter over serial port. Automatically disconnects from any previous connection."""

        self.disconnect()

        connected = False
        reason = ''
        
        try:
            self._serial.port = port
            self._serial.open()
        except serial.SerialException:
            connected = False
            reason = 'Could not open serial port'
        else:
            if test:
                if self._runcmd('i') == 'mph Meter':
                    connected = True
                else:
                    connected = False
                    reason = 'mph Meter did not respond at given serial port'
            else:
                connected = True

        if connected is not True and self._serial.is_open:
            self._serial.close()

        return connected, reason

    def disconnect(self):
        if self._serial.is_open:
            self._serial.close()

    @classmethod
    def flash_fw(cls, port):
        """Classmethod for programming Firmware into a potentially unprogrammed mph Meter. User has to press the Reset button on the Arduino and release it right after calling this function"""
        
        avrdude = subprocess.Popen(
            [
                os.path.abspath(os.path.join('.', 'avrdude', 'avrdude.exe')),
                 '-C', os.path.abspath(os.path.join('.', 'avrdude', 'avrdude.conf')),
                 '-v',
                 '-p', 'atmega328p',
                 '-c', 'arduino',
                 '-P', '{}'.format(port),
                 '-b', '115200',
                 '-D',
                 '-U', 'flash:w:{}:i'.format(os.path.abspath(os.path.join('.', 'mph_meter.ino.standard.hex'))),
                 ],
            encoding='ASCII',
            errors='ignore'
            )
        
        try:
            avrdude.wait(10)
        except subprocess.TimeoutExpired:
            avrdude.kill()
            return False

        if avrdude.returncode != 0:
            return False
        else:
            return True

    def set_defaults(self):
        """Programm mph Meter defaults"""
        
        self.set_debounce(DEFAULTS['debounce_ms'])
        self.set_muempp(DEFAULTS['muempp_µm'])
        self.set_vcrit(DEFAULTS['vwarn_v'])

    def read(self):
        """Read settings from mph Meter"""
        
        reply = self._runcmd('r')
        parts = reply.split(';')
        if len(parts) != 5:
            raise ReplyError('Incorrect reply received (Number of items missmatched).', parts)

        try:
            parts[0] = int(parts[0])
            parts[1] = int(parts[1])
            parts[2] = str(parts[2])
            parts[3] = float(parts[3])/1000
            parts[4] = float(parts[4])/1000
        except ValueError:
            raise ReplyError('Could not convert data.', parts)

        return parts

    def set_debounce(self, value):
        """Set additional software debounce time in miliseconds"""
        
        self._setvalue('d{:d}'.format(value), value, 'debounce time (ms)', 0, 999999, 'ms')

    def set_muempp(self, value):
        """Set µm/pulse"""
        
        self._setvalue('m{:d}'.format(value), value, 'µm per Pulse', 0, 999999999, 'µm/pulse')
        
    def set_vcrit(self, value):
        """Set V(crit). If the supply voltage of the mph Meter is below this threshold during startup, a warning message will be displayed on the LCD"""
        
        self._setvalue('t{:d}'.format(int(value*1000)), value, 'V(crit)', 0, 15, 'V')

    #Boolean var indicating wether an instance is connected or not
    is_connected = property(lambda x: x._serial.is_open)


#View
class TkApp(tk.Tk):
    """Tkinter GUI window"""
    
    def __init__(self):
        super().__init__()

        #Model instance
        self.mphmeter = MphMeter()

        #tkinter variables
        self.variables = {
            'port': tk.StringVar(),
            'version' : tk.StringVar(),
            'vbat_v' : tk.DoubleVar(),
            'muempp_µm' : tk.IntVar(),
            'debounce_ms' : tk.IntVar(),
            'vwarn_v' : tk.DoubleVar(),
            }

        #Validation commands for entries
        vcmd_int = (self.register(lambda x: self._validate_type(x, int)), '%P')
        vcmd_float = (self.register(lambda x: self._validate_type(x, float)), '%P')

        #tkinter widgets
        self.widgets = {
            'port' : [
                ttk.Label(self, text='COM-Port:'),
                ttk.Combobox(self, textvariable=self.variables['port'], state='readonly', postcommand=self._refresh_ports),
                ttk.Button(self, text='Connect', command=self._onconnect),
                ],
            'buttons' : [
                ttk.Button(self, text='Read Values', command=self._read_values, state='disabled'),
                ttk.Button(self, text='Restore Defaults', command=self._ondefault, state='disabled'),
                ttk.Button(self, text='Flash FW', command=self._onfwupdate),
                ],
            'version' : [
                ttk.Label(self, text='SW Version:'),
                ttk.Entry(self, state='disabled', textvariable=self.variables['version']),
                ],
            'vbat_V': [
                ttk.Label(self, text='Battery Voltage:'),
                ttk.Entry(self, state='disabled', textvariable=self.variables['vbat_v']),
                ],
            'muempp_µm': [
                ttk.Label(self, text='µm/pules (µm):'),
                ttk.Spinbox(self, textvariable=self.variables['muempp_µm'], increment=1, from_=0, to=999999999, validate='key', validatecommand=vcmd_int),
                ttk.Button(self, text='Set', command=lambda : self._setvalue(self.variables['muempp_µm'], self.mphmeter.set_muempp), state='disabled'),
                ],
            'debounce_ms': [
                ttk.Label(self, text='SW debounce time (ms):'),
                ttk.Spinbox(self, textvariable=self.variables['debounce_ms'], increment=1, from_=0, to=999999, validate='key', validatecommand=vcmd_int),
                ttk.Button(self, text='Set', command=lambda : self._setvalue(self.variables['debounce_ms'], self.mphmeter.set_debounce), state='disabled'),
                ],
            'vwarn_v':[
                ttk.Label(self, text='Battery warning threshold (V):'),
                ttk.Spinbox(self, textvariable=self.variables['vwarn_v'], increment=0.1, from_=0, to=15, validate='key', validatecommand=vcmd_float),
                ttk.Button(self, text='Set', command=lambda : self._setvalue(self.variables['vwarn_v'], self.mphmeter.set_vcrit), state='disabled'),
                ],
            }

        #Widgets that will only be enabled when connected to mph Meter
        self._need_connection = [
            self.widgets['buttons'][0],
            self.widgets['buttons'][1],
            self.widgets['muempp_µm'][2],
            self.widgets['debounce_ms'][2],
            self.widgets['vwarn_v'][2],
            ]

        #Grid widgets
        self.grid_columnconfigure(1, weight=1)
        for row, what in enumerate(self.widgets.items()):
            name, widgets = what
            for column, widget in enumerate(widgets):
                widget.grid(row=row, column=column, sticky='nesw', padx=1, pady=1)

        #Window configuration
        self.title(__title__)
        self.center()
        self.resizable(False, False)
        self.after(100, lambda: messagebox.showinfo(__title__, 'Configuration Tool for mph Meter.\nWritten by {}.\nVersion {}'.format(__author__, __version__)))

    def center(self):
        """Place window in the middle of the first screen"""
        
        self.update()
        w, h = tuple(int(pos) for pos in self.geometry().split('+')[0].split('x'))
        xpos = self.winfo_screenwidth() // 2 - w // 2
        ypos = self.winfo_screenheight() // 2 - h // 2
        self.geometry('{}x{}+{}+{}'.format(w,h,xpos,ypos))

    def _onconnect(self):
        """Command for Connect Button"""
        
        port = self.variables['port'].get()

        if port == '':
            messagebox.showwarning('ERROR', 'Select port before opening!')
            return
        
        connected, reason = self.mphmeter.connect(port)
        
        if not connected is True:
            messagebox.showerror('ERROR', reason)
        else:
            for widget in self._need_connection:
                widget.configure(state='enabled')
                
            self._read_values()
            messagebox.showinfo('Success', 'Successfully connected to Mph Meter at {}'.format(port))

    def _disconnect(self):
        """Called upon communication loss to disable widgets that require an established connection"""
        
        self.mphmeter.disconnect()
        
        for widget in self._need_connection:
            widget.configure(state='disabled')

    def _ondefault(self):
        """Command for the Restore Defaults button"""
        
        if not self.mphmeter.is_connected:
            messagebox.showwarning('ERROR', 'Connect to mph Meter over COM-Port first!')
            return

        try:
            self.mphmeter.set_defaults()
            self._read_values()

            messagebox.showinfo('Success', 'Restored Defaults')

        except ReplyError as e:
            messagebox.showerror('ERROR', e.text)
        except LostConnectionError:
            messagebox.showerror('ERROR', 'Connection to mph Meter lost! Please reconnect.')
            self._disconnect()

    def _onfwupdate(self):
        """Command for the Flash FW button"""
        
        self._disconnect()
        port = self.variables['port'].get()

        if port == '':
            messagebox.showwarning('ERROR', 'Select port before opening!')
            return

        messagebox.showwarning('Info', 'Press the RESET button of the ARDUINO and release it right after clicking the OK button.')

        if MphMeter.flash_fw(port) is True:
            messagebox.showinfo('Info', 'Firmware update successfull!\nPlease update values or restore defaults MANUALLY!')
        else:
            messagebox.showerror('ERROR', 'Firmware update failed!')

    def _read_values(self):
        """Command for the Read Values button"""
        
        if not self.mphmeter.is_connected:
            messagebox.showwarning('ERROR', 'Connect to mph Meter over COM-Port first!')
            return

        try:
            values = self.mphmeter.read()
            
            self.variables['muempp_µm'].set(values[0])
            self.variables['debounce_ms'].set(values[1])
            self.variables['version'].set(values[2])
            self.variables['vwarn_v'].set(values[3])
            self.variables['vbat_v'].set(values[4])
            
        except ReplyError as e:
            messagebox.showerror('ERROR', e.text)
        except LostConnectionError:
            messagebox.showerror('ERROR', 'Connection to mph Meter lost! Please reconnect.')
            self._disconnect()

    def _refresh_ports(self):
        """Refresh list of available serial ports for Combobox. Called every time the Combobox is clicked"""
        
        self.widgets['port'][1].configure(values = [x.device for x in serialports.comports()])

    def _setvalue(self, var, setfunc):
        """Command for the Set buttons. (They use lambdas to fill the var and setfunc variables)"""
        
        if not self.mphmeter.is_connected:
            messagebox.showwarning('ERROR', 'Connect to mph Meter over COM-Port first!')
            return

        try:
            value = var.get()
        except tk.TclError:
            messagebox.showwarning('ERROR', 'Fill field before setting value!')
            return
        
        try:
            setfunc(value)
        except ReplyError:
            messagebox.showerror('ERROR', 'Could not set new v_warn value!')
        except LostConnectionError:
            messagebox.showerror('ERROR', 'Connection to mph Meter lost! Please reconnect.')
            self._disconnect()
        except BoundaryError as e:
            messagebox.showerror('ERROR', e.text)

    def _validate_type(self, value, _type):
        """Function for input validation"""
        
        if value == '':
            return True
        try:
            _type(value)
        except ValueError:
            self.bell()
            return False
        return True

    def __del__(self):
        self._serial.close()
        super().__del__()

if __name__ == '__main__':
    """
    parser = argparse.ArgumentParser(descpription=__despription__)
    parser.add_argument('-p', '--port', action='store', choices=[x.device for x in serialports.comports()], required=True, help='Serial port at which the mph Meter is connected.')
    parser.add_argument('--default', action='store_true', help='Programm mph Meter defaults.')
    parser.add_argument('--flashfw', action='store_true', help='Flash Firmware to mph Meter.')
    parser.add_argument('-m', '--muempp', action='store', help='Programm µm/pulse value.')
    parser.add_argument('-d', '--debounce', action='store', help='Programm additional Software debounce time value in miliseconds.')
    parser.add_argument('-r', '--read', action='store', help='Programm V(crit.) value.')
    parser.add_argument('--version', action='version', version=__version__)
    """
    app = TkApp()
    app.mainloop()
