# Screenshots (OCR)

Read MoMo messages, and the sender, straight from screenshots. Needs `pip install "cedikit[ocr]"`. Everything runs on your own computer: Windows' built-in OCR on Windows, RapidOCR elsewhere.

!!! tip
    OCR can misread characters. cedikit fixes common slips (`GHS50.OO` becomes `GHS50.00`), but always compare the text with the picture.

::: cedikit.ocr
