"""
Copyright (c) 2011 Justin Bruce Van Horne

Python-Markdown LaTeX Extension
===============================

A LaTeX extension for Python-Markdown. 
Adds support for $math mode$ and %text mode%. This plugin supports
multiline equations/text.

The actual image generation is done via LaTeX/DVI output.
It encodes data as base64 so there is no need for images directly.
All the work is done in the preprocessor.
"""

import markdown
import re
import os
import string
import base64
import tempfile
from subprocess import call, PIPE

TEX_MODE = re.compile(r'(?=(?<!\\)\%).(.+?)(?<!\\)\%', re.MULTILINE | re.DOTALL)
MATH_MODE = re.compile(r'(?=(?<!\\)\$).(.+?)(?<!\\)\$', re.MULTILINE | re.DOTALL)
PREAMBLE_MODE = re.compile(r'(?=(?<!\\)\%\%).(.+?)(?<!\\)\%\%', re.MULTILINE | re.DOTALL)
IMG_EXPR = "<img class='latex-inline math-%s' alt='%s' id='%s'" + \
        " src='data:image/png;base64,%s'>"


# These are our cached expressions that are stored in latex.cache
cached = {}


# Basic LaTex Setup as well as our list of expressions to parse
tex_preamble = r""" \documentclass{article}
                    \usepackage{amsmath}
                    \usepackage{amsthm}
                    \usepackage{amssymb}
                    \usepackage{bm}
                    \usepackage[usenames,dvipsnames]{color}
                    \pagestyle{empty}
                    """


class TeXPreprocessor(markdown.preprocessors.Preprocessor):
    """The TeX preprocessor has to run prior to all the actual processing
    and can not be parsed in block mode very sanely."""
    def _tex_to_base64(self, tex, math_mode):
        """Generates a base64 representation of TeX string"""
        # Generate the temporary file
    	tempfile.tempdir = "./"
        path = tempfile.mktemp()
        tmp_file = open(path, "w")
        tmp_file.write(tex_preamble)


        # Figure out the mode that we're in
        if math_mode:
            tmp_file.write("$%s$" % tex)
        else:
            tmp_file.write("%s" % tex)

        tmp_file.write('\end{document}')
        tmp_file.close()

        # compile LaTeX document. A DVI file is created
        status = call(('rubber %s' % path).split(), stdout=PIPE)
        
        # clean up if the above failed
        if status:
            self._cleanup(path, err=True)
            raise Exception("Couldn't compile LaTeX document")

        # Run dvipng on the generated DVI file. Use tight bounding box.
        # Magnification is set to 1200
        dvi = "%s.dvi" % path
        png = "%s.png" % path

        # Extract the image
        cmd = "dvipng -T tight -x 1200 -z 9 \
                %s -o %s" % (dvi, png)
        status = call(cmd.split(), stdout=PIPE)

        # clean up if we couldn't make the above work
        if status:
            self._cleanup(path, err=True)
            raise Exception("Couldn't convert LaTeX to image")

        # Read the png and encode the data
        png = open(png, "rb")
        data = png.read()
        data = base64.b64encode(data)
        png.close()

    	self._cleanup(path)

        return data

    def _cleanup(self, path, err=False):
        # don't clean up the log if there's an error
        if err: extensions = ["", ".aux", ".dvi", ".png"]
        else: extensions = ["", ".log", ".aux", ".dvi", ".png"]

        # now do the actual cleanup, passing on non-existent files
        for extension in extensions:
            try: os.remove("%s%s" % (path, extension))
            except IOError: pass

    def run(self, lines):
        """Parses the actual page"""
        # Re-creates the entire page so we can parse in a multine env.
        page = "\n".join(lines)
        global tex_preamble

        # Adds a preamble mode
        preambles = PREAMBLE_MODE.findall(page)
        for preamble in preambles:
            tex_preamble += preamble + "\n"
            page = PREAMBLE_MODE.sub("", page, 1)
        tex_preamble += "\\begin{document}"

        # Figure out our text strings and math-mode strings
        tex_expr = [(TEX_MODE, False, x) for x in TEX_MODE.findall(page)]
        tex_expr += [(MATH_MODE, True, x) for x in MATH_MODE.findall(page)]

        # Parse the expressions
        new_cache = {}
        for reg, math_mode, expr in tex_expr:
            simp_expr = filter(unicode.isalnum, expr)
            if simp_expr in cached:
                data = cached[simp_expr]
            else:
                data = self._tex_to_base64(expr, math_mode)
                new_cache[simp_expr] = data
            expr = expr.replace('"', "").replace("'", "")
            page = reg.sub(IMG_EXPR %
                    (str(math_mode).lower(), re.escape(expr), 
                        simp_expr[:15], data), page, 1)

        # Cache our data
        cache_file = open('latex.cache', 'a')
        for key, value in new_cache.items():
            cache_file.write("%s %s\n" % (key, value))
        cache_file.close()

        # Make sure to resplit the lines
        return page.split("\n")


class MarkdownLatex(markdown.Extension):
    """Wrapper for TeXPreprocessor"""
    def extendMarkdown(self, md, md_globals):
        md.preprocessors.add('latex', TeXPreprocessor(self), ">html_block")


def makeExtension(configs=None):
    """Wrapper for a MarkDown extension"""
    try:
        cache_file = open('latex.cache', 'r+')
        for line in cache_file.readlines():
            key, val = line.strip("\n").split(" ")
            cached[key] = val
    except IOError:
        pass
    return MarkdownLatex(configs=configs)
