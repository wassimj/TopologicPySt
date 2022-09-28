import topologic
import json

def processItem(item, overwrite):
	hbModel, filepath = item
	# Make sure the file extension is .hbjson
	ext = filepath[len(filepath)-7:len(filepath)]
	if ext.lower() != ".hbjson":
		filepath = filepath+".hbjson"
	f = None
	try:
		if overwrite == True:
			f = open(filepath, "w")
		else:
			f = open(filepath, "x") # Try to create a new File
	except:
		raise Exception("Error: Could not create a new file at the following location: "+filepath)
	if (f):
		json.dump(hbModel.to_dict(), f, indent=4)
		f.close()	
		return True
	return False


