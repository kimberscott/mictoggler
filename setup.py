# run 
# python setup.py py2exe
# to create executable.

from distutils.core import setup
import py2exe
from glob import glob
import sys

sys.path.append("C:\\Users\\Kim\\Google Drive\\mictoggler\\dist\\dlls")

data_files = [("x86_microsoft.vc90.crt", glob(r'C:\Users\Kim\Google Drive\mictoggler\dist\dlls\*.*'))]

setup(data_files=data_files, console=['mictoggler.py'])