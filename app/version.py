PHASE = 5
VERSION = "1.0.6"       # the number the updater compares (keep it in step with installer.iss and version_info.txt)
STAGE = "BETA"
CREATOR = "itsmeblitz"
PRODUCT_NAME = "CHATDOOM"


def label():
    return "Phase %d \u00b7 v%s (%s)" % (PHASE, VERSION, STAGE)
