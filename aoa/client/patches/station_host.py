"""The startup Station hostname field of the 2.9.2 client.

The login dialog disables Play Online until its asynchronous lookup succeeds;
the original aoahost.com lookup fails and never re-enables the button.
prepare writes the Station chosen by the player into this fixed-width field
(prepare.host_field validates it); it is not a patch with on and off bytes.
"""
OFFSET = 0x1C5C60
ORIGINAL = b"aoahost.com\0"
LOCAL = b"localhost\0\0\0"
