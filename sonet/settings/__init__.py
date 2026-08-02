


try:
	from .local import *
except Exception as e:
	# print("LOCAL FAIL")
	# print(str(e))
	from .production import *