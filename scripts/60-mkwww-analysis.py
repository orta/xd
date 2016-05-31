#!/usr/bin/env python3

# Usage:
#   $0 [-c corpus] -o output_dir <input.xd> <sources.tsv>
#
# outputs html analysis page with similar grids/clues/answers
#

from queries.similarity import find_similar_to, find_clue_variants, load_clues, load_answers, grid_similarity
from xdfile.utils import get_args, open_output, find_files, log, debug, get_log, COLUMN_SEPARATOR, EOL, parse_tsv, progress, parse_pathname
from xdfile.html import th, html_select_options
from xdfile import xdfile, corpus, ClueAnswer, BLOCK_CHAR
import time
import cgi

def xd_to_html(xd, compare_with=None):
    r = '<div class="fullgrid">'

    similarity_pct = ''
    if compare_with:
        real_pct = grid_similarity(xd, compare_with)
        if real_pct < 25:
            return ''

        similarity_pct = " (%d%%)" % real_pct

    r += '<div class="xdid"><a href="/pub/%s/%s/%s">%s %s</a></div>' % (xd.publication_id(), xd.year(), xd.xdid(), xd.xdid(), similarity_pct)
    r += headers_to_html(xd)
    r += grid_to_html(xd, compare_with)

    r += '</div>' # solution
    return r

def headers_to_html(xd):
    # headers
    r = '<div class="xdheaders"><ul class="xdheaders">'
    for k, v in xd.iterheaders():
        r += '<li class="%s">%s: <b>%s</b></li>' % (k, k, v)
    r += '</ul></div>'
    return r


def grid_to_html(xd, compare_with=None):
    "htmlify this puzzle's grid"

    grid_html = '<div class="xdgrid">'
    for r, row in enumerate(xd.grid):
        grid_html += '<div class="xdrow">'
        for c, cell in enumerate(row):
            classes = [ "xdcell" ]

            if cell == BLOCK_CHAR:
                classes.append("block")

            if compare_with and cell == compare_with.cell(r, c):
                classes.append("same")

            grid_html += '<div class="%s">' % " ".join(classes)
            grid_html += cell  # TODO: expand rebus
            #  include other mutations that would still be valid
            grid_html += '</div>' # xdcell
        grid_html += '</div>' #  xdrow
    grid_html += '</div>' # xdgrid

    return grid_html


# pairs of ("option", num_uses)
def html_select(options, top_option=""):
    if not options:
        return str(top_option)

    r = '<div class="actuals">'

    r += '<select>'
    if top_option:
        r += '<option>%s</option>' % top_option

    for opt, n in sorted(options, key=lambda x: x[1], reverse=True):
        r += '<option>'

        s = esc(str(opt))
        
        if n > 1:
            r += '%s [x%d]' % (s, n)
        else:
            r += s

        r += '</option>'
    r += '</select></div>'
    r += '<div class="num"> %d</div>' % len(options)
    return r

def esc(s):
    return cgi.escape(s)

def main():
    args = get_args("annotate puzzle clues with earliest date used in the corpus")
    outf = open_output()

    similar = parse_tsv("similar.tsv", "Similar") # by xdid

    for fn, contents in find_files(*args.inputs, ext=".xd"):
        mainxd = xdfile(contents.decode('utf-8'), fn)

        similar_grids = sorted(find_similar_to(mainxd, corpus()), key=lambda x: x[0], reverse=True)

        log("finding similar clues")
        clues_html = '<table class="clues">' + th('grid', 'original clue and previous uses', 'answers for this clue', 'other clues for this answer')

        mainpubid = mainxd.publication_id()
        maindate = mainxd.date()

        nstaleclues = 0
        nstaleanswers = 0
        ntotalclues = 0

        for pos, mainclue, mainanswer in mainxd.clues:
            progress(mainanswer)

            poss_answers = []
            pub_uses = { }  # [pubid] -> set(ClueAnswer)

            mainca = ClueAnswer(mainpubid, maindate, mainanswer, mainclue)

            clues_html += '<tr><td class="pos">%s%s.</td>' % pos

            for clueans in find_clue_variants(mainclue):
                if clueans.answer != mainanswer:
                    poss_answers.append(clueans)

                if clueans.answer == mainanswer:
                    if clueans.pubid in pub_uses:
                        otherpubs = pub_uses[clueans.pubid]
                    else:
                        otherpubs = set()  # set of ClueAnswer
                        pub_uses[clueans.pubid] = otherpubs

                    otherpubs.add(clueans)

            stale = False
            clues_html += '<td class="other-uses">'
            if len(pub_uses) > 0:
                sortable_uses = []
                for pubid, uses in pub_uses.items():
                    # show the earlist unboiled clue
                    for u in sorted(uses, key=lambda x: x.date or ""):
                        # only show those published earlier
                        if u.date and u.date <= maindate:
                            if pubid == mainpubid and u.date == maindate:
                                pass
                            else:
                                stale = True
                                sortable_uses.append((u.date, u, 1))

                clues_html += html_select([ (clue, nuses) for dt, clue, nuses in sorted(sortable_uses, key=lambda x: x[0], reverse=True) ], top_option=mainclue)

            else:
                clues_html += '<div class="original">%s</div>' % esc(mainclue)
        
            clues_html += '</td>'
            clues_html += '<td class="other-answers">'
            clues_html += html_select_options(poss_answers, strmaker=lambda ca: ca.answer, force_top=mainca)
            clues_html += '</td>'

            clues_html += '<td class="other-clues">'

            # bclues is all boiled clues for this particular answer: { [bc] -> #uses }
            bclues = load_answers().get(mainanswer, [])
            stale_answer = False
            if bclues:
                uses = []
                for bc, nuses in bclues.items():
                    # then find all clues besides this one
                    clue_usages = [ ca for ca in load_clues().get(bc, []) if ca.answer == mainanswer and ca.date < maindate ]

                    if clue_usages:
                        stale_answer = True
                        if nuses > 1:
                            # only use one (the most recent) ClueAnswer per boiled clue
                            # but use the clue only (no xdid)
                            ca = sorted(clue_usages, key=lambda ca: ca.date or "z")[-1].clue
                        else:
                            ca = sorted(clue_usages, key=lambda ca: ca.date or "z")[-1]
                        uses.append((ca, nuses))

                if uses:
                    clues_html += html_select(uses)

            clues_html += '</td>'

            clues_html += '</tr>'

            if stale_answer:
                nstaleanswers += 1
            if stale:
                nstaleclues += 1
            ntotalclues += 1

            
        clues_html += '</table>'

        # similar grids
        main_html = '<div class="grids">'
        main_html += xd_to_html(mainxd)

        # dump miniature grids with highlights of similarities
        r = similar[mainxd.xdid()]
        for xdid in r.similar_grids.split():
            main_html += '<div class="similar-grid">' + xd_to_html(xd2, mainxd)
            main_html += '</div>'
            main_html += '</div>'

        main_html += '</div>'


        # clue analysis
        main_html += '<div class="clues">'
        main_html += '<h2>%d%% reused clues (%s/%s)</h2>' % (nstaleclues*100.0/ntotalclues, nstaleclues, ntotalclues)
        main_html += '<ul>' + clues_html + '</ul>'
        main_html += '</div>'

        # summary row
        outf.write_row('similar.tsv', 'xdid similar_grid_pct reused_clues reused_answers total_clues', [
            mainxd.xdid(),
            int(100*sum(pct/100.0 for pct, xd1, xd2 in similar_grids)),
            nstaleclues,
            nstaleanswers,
            ntotalclues
            ])

        outf.write_html("pub/%s/%s/%s/index.html" % (mainxd.publication_id(), mainxd.year(), mainxd.xdid()), main_html, title="xd analysis of %s" % mainxd.xdid())


main()


