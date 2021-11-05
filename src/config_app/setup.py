from cx_Freeze import setup, Executable

import mph_meter_configurator as source

# Dependencies are automatically detected, but it might need
# fine tuning.
buildOptions = dict(
    packages = [
        "tkinter",
        "io",
        "time",
        "os",
        "itertools",
        "serial",
        "re",
        "threading",
        ],
    excludes = [
        "asyncio",
        #"collections",
        "concurrent",
        #"ctypes",
        "email",
        #"encodings",
        "html",
        "http",
        #"importlib",
        "logging",
        "multiprocessing",
        "pydoc_data",
        "unittest",
        "urllib",
        "xml",
        "xmlrpc",
        ])

import sys
base = 'Win32GUI' if sys.platform=='win32' else None

executables = [
    Executable(source.__file__, base=base)
]

setup(name=source.__title__,
      version = source.__version__,
      description = source.__description__,
      options = dict(build_exe = buildOptions),
      executables = executables)
