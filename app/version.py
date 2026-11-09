VERSION = "1.4.2"       # the number the updater compares (keep it in step with installer.iss and version_info.txt)
STAGE = "Released"
CREATOR = "ZUNIMILABS"
PRODUCT_NAME = "CHATDOOM"


def label():
    return "v%s \u00b7 %s" % (VERSION, STAGE)
