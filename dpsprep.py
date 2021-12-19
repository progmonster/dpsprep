#!/usr/bin/env python2
# dpsprep - Sony Digital Paper DJVU to PDF converter
# Copyright(c) 2015 Kevin Croker
# GNU GPL v3
#


# python dpsprep.py /mnt/c/Users/progm/Downloads/GTD/GTD-1990-09.djvu GTD-1990-09.pdf


import sexpdata
import os
import pipes
import subprocess
import re

# Recursively walks the sexpr tree and outputs a metadata format understandable by pdftk
def walk_bmarks(bmarks, level):
    output = ''
    wroteTitle = False
    for j in bmarks:
        if isinstance(j, list):
            output = output + walk_bmarks(j, level + 1)
        elif isinstance(j, str):
            if not wroteTitle:
                output = output + "BookmarkBegin\nBookmarkTitle: %s\nBookmarkLevel: %d\n" % (j, level)
                wroteTitle = True
            else:
                output = output + "BookmarkPageNumber: %s\n" % j.split('#')[1]
                wroteTitle = False
        else:
            pass
    return output

# quality: specify JPEG lossy compression quality (50-150).  See man ddjvu for more information.
def main(src, dest, quality = 80):
    home = os.path.expanduser("~")

    if not os.path.exists(home + "/.dpsprep"):
        os.mkdir(home + "/.dpsprep")

    tmp = home + "/.dpsprep"

    # Reescape the filenames because we will just be sending them to commands via system
    # and we don't otherwise work directly with the DJVU and PDF files.
    # Also, stash the temp pdf in the clean spot
    src = pipes.quote(src)
    finaldest = pipes.quote(dest)
    dest = home + '/.dpsprep/' + pipes.quote(dest)

    # Check for a file presently being processed
    if os.path.isfile(tmp + '/inprocess'):
        fname = open(tmp + '/inprocess', 'r').read()
        if not fname == src:
            print("ERROR: Attempting to process %s before %s is completed. Aborting." % (src, fname))
            exit(3)
        else:
            print("NOTE: Continuing to process %s..." % src)
    else:
        # Record the file we are about to process
        open(tmp + '/inprocess', 'w').write(src)

    # Make the PDF, compressing with JPG so they are not ridiculous in size
    # (cwd)
    if not os.path.isfile(tmp + '/dumpd'):
        retval = os.system("ddjvu -v -eachpage -quality=%d -format=tiff %s %s/pg%%06d.tif" % (quality, src, tmp))
        if retval > 0:
            print("\nNOTE: There was a problem dumping the pages to tiff.  See above output")
            exit(retval)

        print("Flat PDF made.")
        open(tmp + '/dumpd', 'a').close()
    else:
        print("Inflated PDFs already found, using these...")

    # Extract and embed the text
    if not os.path.isfile(tmp + '/hocrd'):
        cnt = int(subprocess.check_output("djvused %s -u -e n" % src, shell=True))

        for i in range(1, cnt):
            retval = os.system("djvu2hocr -p %d %s | sed 's/ocrx/ocr/g' > %s/pg%06d.html" % (i, src, tmp, i))
            if retval > 0:
                print("\nNOTE: There was a problem extracting the OCRd text on page %d, see above output." % i)
                exit(retval)

        print("OCRd text extracted.")
        open(tmp + '/hocrd', 'a').close()
    else:
        print("Using existing hOCRd output...")

    # Is sloppy and dumps to present directory
    if not os.path.isfile(tmp + '/beadd'):
        cwd = os.getcwd()
        os.chdir(tmp)
        retval = os.system('pdfbeads * > ' + dest)
        if retval > 0:
            print("\nNOTE: There was a problem beading, see above output.")
            exit(retval)

        print("Beading complete.")
        open('beadd', 'a').close()
        os.chdir(cwd)
    else:
        print("Existing destination found, assuming beading already complete...")

    ###########################$
    #
    # At this point, the OCRd text is now properly placed within the PDF file.
    # Now, we need to add the links and table of contents!
    # Extract the bookmark data from the DJVU document
    # (scratch)
    retval = 0
    retval = retval | os.system("djvused %s -u -e 'print-outline' > %s/bmarks.out" % (src, tmp))
    print("Bookmarks extracted.")
    # Check for zero-length outline

    if os.stat("%s/bmarks.out" % tmp).st_size > 0:
        # Extract the metadata from the PDF document
        retval = retval | os.system("pdftk %s dump_data_utf8 > %s/pdfmetadata.out" % (dest, tmp))
        print("Original PDF metadata extracted.")

        # Parse the sexpr
        pdfbmarks = walk_bmarks(sexpdata.load(open(tmp + '/bmarks.out')), 0)

        # Integrate the parsed bookmarks into the PDF metadata
        p = re.compile('NumberOfPages: [0-9]+')
        metadata = open("%s/pdfmetadata.out" % tmp, 'r').read()

        for m in p.finditer(metadata):
            loc = int(m.end())

            newoutput = metadata[:loc] + "\n" + pdfbmarks[:-1] + metadata[loc:]

            # Update the PDF metadata
            open("%s/pdfmetadata.in" % tmp, 'w').write(newoutput)
            retval = retval | os.system(
                "pdftk %s update_info_utf8 %s output %s" % (dest, tmp + '/pdfmetadata.in', finaldest))
    else:
        retval = retval | os.system("mv %s %s" % (dest, finaldest))
        print("No bookmarks were present!")

    # If retval is shit, don't delete temp files
    if retval == 0:
        os.system("rm %s/*" % tmp)
        print("SUCCESS. Temporary files cleared.")
        exit(0)
    else:
        print(
            "There were errors in the metadata step.  OCRd text is fine, pdf is almost ready.  See above output for cluse")
        exit(retval)

main('/mnt/c/Users/progm/Downloads/GTD/GTD-1988-11.djvu', 'GTD-1988-11.80.pdf', 80)
