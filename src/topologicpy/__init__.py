
import sys
import os, re
from sys import platform

if platform == 'win32':
    os_name = 'windows'
else:
    os_name = 'linux'

sitePackagesFolderName = os.path.join(os.path.dirname(os.path.realpath(__file__)), "bin", os_name)
test1 = os.path.join(os.path.dirname(os.path.realpath(__file__)), "bin")
print(os.listdir(test1))
topologicFolderName = [filename for filename in os.listdir(sitePackagesFolderName) if filename.startswith("topologic")][0]
topologicPath = os.path.join(sitePackagesFolderName, topologicFolderName)
sys.path.append(topologicPath)

import topologic
