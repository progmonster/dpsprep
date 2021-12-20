#!/usr/bin/env python2
# dpsprep - Sony Digital Paper DJVU to PDF converter
# Copyright(c) 2015 Kevin Croker
# GNU GPL v3
#


# python dpsprep.py /mnt/c/Users/progm/Downloads/GTD/GTD-1990-09.djvu GTD-1990-09.pdf
# main('/mnt/c/Users/progm/Downloads/GTD/GTD-1988-10.djvu', './123/GTD-1988-10.80.pdf', 80)


import sexpdata
import os
import pipes
import subprocess
import re
from pathlib import Path


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
def convert_file(src, dest, quality=80):
    home_dir = os.path.expanduser("~")

    if not os.path.exists(home_dir + "/.dpsprep"):
        os.mkdir(home_dir + "/.dpsprep")

    tmp_dir = home_dir + "/.dpsprep"

    # Reescape the filenames because we will just be sending them to commands via system
    # and we don't otherwise work directly with the DJVU and PDF files.
    # Also, stash the temp pdf in the clean spot
    src_quoted = pipes.quote(src)
    dest_quoted = pipes.quote(dest)
    dest_dir_quoted = os.path.dirname(dest_quoted)
    dest_file_name_quoted = os.path.basename(dest_quoted)
    tmp_dest = home_dir + '/.dpsprep/' + pipes.quote(dest_file_name_quoted)

    # Check for a file presently being processed
    if os.path.isfile(tmp_dir + '/inprocess'):
        fname = open(tmp_dir + '/inprocess', 'r').read()
        if not fname == src_quoted:
            print("ERROR: Attempting to process %s before %s is completed. Aborting." % (src_quoted, fname))
            return 3
        else:
            print("NOTE: Continuing to process %s..." % src_quoted)
    else:
        # Record the file we are about to process
        open(tmp_dir + '/inprocess', 'w').write(src_quoted)

    # Make the PDF, compressing with JPG so they are not ridiculous in size
    # (cwd)
    if not os.path.isfile(tmp_dir + '/dumpd'):
        retval = os.system(
            "ddjvu -v -eachpage -quality=%d -format=tiff %s %s/pg%%06d.tif" % (quality, src_quoted, tmp_dir))
        if retval > 0:
            print("\nNOTE: There was a problem dumping the pages to tiff.  See above output")
            return retval

        print("Flat PDF made.")
        open(tmp_dir + '/dumpd', 'a').close()
    else:
        print("Inflated PDFs already found, using these...")

    # Extract and embed the text
    if not os.path.isfile(tmp_dir + '/hocrd'):
        cnt = int(subprocess.check_output("djvused %s -u -e n" % src_quoted, shell=True))

        for i in range(1, cnt):
            retval = os.system("djvu2hocr -p %d %s | sed 's/ocrx/ocr/g' > %s/pg%06d.html" % (i, src_quoted, tmp_dir, i))
            if retval > 0:
                print("\nNOTE: There was a problem extracting the OCRd text on page %d, see above output." % i)
                return retval

        print("OCRd text extracted.")
        open(tmp_dir + '/hocrd', 'a').close()
    else:
        print("Using existing hOCRd output...")

    # Is sloppy and dumps to present directory
    if not os.path.isfile(tmp_dir + '/beadd'):
        cwd = os.getcwd()
        os.chdir(tmp_dir)
        retval = os.system('pdfbeads * > ' + tmp_dest)
        if retval > 0:
            print("\nNOTE: There was a problem beading, see above output.")
            return retval

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
    retval = retval | os.system("djvused %s -u -e 'print-outline' > %s/bmarks.out" % (src_quoted, tmp_dir))
    print("Bookmarks extracted.")
    # Check for zero-length outline

    if os.stat("%s/bmarks.out" % tmp_dir).st_size > 0:
        # Extract the metadata from the PDF document
        retval = retval | os.system("pdftk %s dump_data_utf8 > %s/pdfmetadata.out" % (tmp_dest, tmp_dir))
        print("Original PDF metadata extracted.")

        # Parse the sexpr
        pdfbmarks = walk_bmarks(sexpdata.load(open(tmp_dir + '/bmarks.out')), 0)

        # Integrate the parsed bookmarks into the PDF metadata
        p = re.compile('NumberOfPages: [0-9]+')
        metadata = open("%s/pdfmetadata.out" % tmp_dir, 'r').read()

        for m in p.finditer(metadata):
            loc = int(m.end())

            newoutput = metadata[:loc] + "\n" + pdfbmarks[:-1] + metadata[loc:]

            # Update the PDF metadata
            open("%s/pdfmetadata.in" % tmp_dir, 'w').write(newoutput)
            retval = retval | os.system(
                "pdftk %s update_info_utf8 %s output %s" % (tmp_dest, tmp_dir + '/pdfmetadata.in', dest_quoted))
    else:
        retval = retval | os.system("mkdir -p %s" % dest_dir_quoted)
        retval = retval | os.system("mv %s %s" % (tmp_dest, dest_quoted))
        print("No bookmarks were present!")

    # If retval is shit, don't delete temp files
    if retval == 0:
        os.system("rm %s/*" % tmp_dir)
        print("SUCCESS. Temporary files cleared.")
        return 0
    else:
        print(
            "There were errors in the metadata step.  OCRd text is fine, pdf is almost ready.  See above output for cluse")
        return retval


def convert_file_into_the_same_place(djvu_file, quality=80):
    pdf_file_name = os.path.splitext(os.path.basename(djvu_file))[0] + ".pdf"

    convert_file(djvu_file, os.path.join(os.path.dirname(djvu_file), pdf_file_name), quality)


def convert_in_dir(dir, quality=80):
    for path in Path(dir).rglob("*.djvu"):
        convert_file_into_the_same_place(str(path.absolute()), quality)

# convert_file('/mnt/c/Users/progm/Downloads/GTD/GTD-1988-09.djvu', './123/GTD-1988-09.2.pdf', 80)
# convert_file_into_the_same_place('/mnt/c/Users/progm/Downloads/GTD/GTD-1988-03.djvu', 80)
# convert_in_dir("/mnt/c/Users/progm/Downloads/GTD", 80)
