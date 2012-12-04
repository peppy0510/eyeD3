# -*- coding: utf-8 -*-
################################################################################
#  Copyright (C) 2009  Travis Shirk <travis@pobox.com>
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
################################################################################
from __future__ import print_function
import sys, os, operator
from collections import Counter

from eyed3 import id3, mp3
from eyed3.core import AUDIO_MP3
from eyed3.utils import guessMimetype, cli
from eyed3.plugins import LoaderPlugin

ID3_VERSIONS = [id3.ID3_V1_0, id3.ID3_V1_1,
                id3.ID3_V2_2, id3.ID3_V2_3, id3.ID3_V2_4]

_OP_STRINGS = {operator.le: "<=",
               operator.lt: "< ",
               operator.ge: ">=",
               operator.gt: "> ",
               operator.eq: "= ",
               operator.ne: "!=",
              }

class Rule(object):
    def test(self):
        raise NotImplementedError()


PREFERRED_ID3_VERSIONS = [ id3.ID3_V2_3,
                           id3.ID3_V2_4,
                         ]
class Id3TagRules(Rule):
    def test(self, path, audio_file):
        scores = []

        if audio_file is None:
            return None

        if not audio_file.tag:
            return [(-75, "Missing ID3 tag")];

        tag = audio_file.tag
        if tag.version not in PREFERRED_ID3_VERSIONS:
            scores.append((-30, "ID3 version not in %s" %
                                PREFERRED_ID3_VERSIONS))
        if not tag.title:
            scores.append((-30, "Tag missing title"))
        if not tag.artist:
            scores.append((-28, "Tag missing artist"))
        if not tag.album:
            scores.append((-26, "Tag missing album"))
        if not tag.track_num[0]:
            scores.append((-24, "Tag missing track number"))
        if not tag.track_num[1]:
            scores.append((-22, "Tag missing total # of tracks"))

        if not tag.best_release_date:
            scores.append((-30, "Tag missing any useful dates"))
        else:
            if not tag.original_release_date:
                # Original release date is so rarely used but is almost always
                # what I mean or wanna know.
                scores.append((-10, "No original release date"))
            elif not tag.release_date:
                scores.append((-5, "No release date"))

        # TLEN, best gotten from audio_file.info.time_secs but having it in
        # the tag is good, I guess.
        if "TLEN" not in tag.frame_set:
            scores.append((-5, "No TLEN frame"))

        return scores


BITRATE_DEDUCTIONS = [(192, -20), (256, -10)]
class BitrateRule(Rule):
    def test(self, path, audio_file):
        scores = []

        if not audio_file:
            return None

        is_vbr, bitrate = audio_file.info.bit_rate
        for threshold, score in BITRATE_DEDUCTIONS:
            if bitrate < threshold:
                scores.append((score, "Bit rate < %d" % threshold))
                break

        return scores


VALID_MIME_TYPES = mp3.MIME_TYPES + [ "image/png",
                                      "image/gif",
                                      "image/jpeg",
                                    ]
class FileRule(Rule):
    def test(self, path, audio_file):
        mt = guessMimetype(path)

        for name in os.path.split(path):
            if name.startswith('.'):
                return [(-100, "Hidden file type")]

        if mt not in VALID_MIME_TYPES:
            return [(-100, "Unsupported file type: %s" % mt)]
        return None


VALID_ARTWORK_NAMES = ("cover", "cover-front", "cover-back")
class ArtworkRule(Rule):
    def test(self, path, audio_file):
        mt = guessMimetype(path)
        if mt and mt.startswith("image/"):
            name, ext = os.path.splitext(os.path.basename(path))
            if name not in VALID_ARTWORK_NAMES:
                return [(-10, "Artwork file not in %s" %
                              str(VALID_ARTWORK_NAMES))]

        return None


BAD_FRAMES = ["PRIV", "GEOB"]
class Id3FrameRules(Rule):
    def test(self, path, audio_file):
        scores = []
        if not audio_file or not audio_file.tag:
            return

        tag = audio_file.tag
        for fid in tag.frame_set:
            if fid[0] == 'T' and fid != "TXXX" and len(tag.frame_set[fid]) > 1:
                scores.append((-10, "Multiple %s frames" % fid))
            elif fid in BAD_FRAMES:
                scores.append((-13, "%s frames are bad, mmmkay?" % fid))

        return scores


class Stat(Counter):
    TOTAL = "total"

    def __init__(self, *args, **kwargs):
        super(Stat, self).__init__(*args, **kwargs)
        self[self.TOTAL] = 0
        self._key_names = {}

    def compute(self, file, audio_file):
        self[self.TOTAL] += 1
        self._compute(file, audio_file)

    def _compute(self, file, audio_file):
        pass

    def report(self):
        self._report()

    def _sortedKeys(self, most_common=False):
        def keyDisplayName(k):
            return self._key_names[k] if k in self._key_names else k

        key_map = {}
        for k in self.keys():
            key_map[keyDisplayName(k)] = k

        if not most_common:
            sorted_names = list(key_map.keys())
            sorted_names.remove(self.TOTAL)
            sorted_names.sort()
            sorted_names.append(self.TOTAL)
        else:
            most_common = self.most_common()
            sorted_names = []
            remainder_names = []
            for k, v in most_common:
                if k != self.TOTAL and v > 0:
                    sorted_names.append(keyDisplayName(k))
                elif k != self.TOTAL:
                    remainder_names.append(keyDisplayName(k))

            remainder_names.sort()
            sorted_names = sorted_names + remainder_names
            sorted_names.append(self.TOTAL)

        return [key_map[name] for name in sorted_names]

    def _report(self, most_common=False):
        keys = self._sortedKeys(most_common=most_common)

        key_col_width = 0
        val_col_width = 0
        for key in keys:
            key = self._key_names[key] if key in self._key_names else key
            key_col_width = max(key_col_width, len(str(key)))
            val_col_width = max(val_col_width, len(str(self[key])))
        key_col_width += 1
        val_col_width += 1

        for k in keys:
            key_name = self._key_names[k] if k in self._key_names else k
            value = self[k]
            percent = self.percent(k) if value and k != "total" else ""
            print("%(padding)s%(key)s:%(value)s%(percent)s" %
                  { "padding": ' ' * 4,
                    "key":   str(key_name).ljust(key_col_width),
                    "value": str(value).rjust(val_col_width),
                    "percent": " ( %s%.2f%%%s )" %
                                 (cli.GREEN, percent, cli.RESET) if percent
                                                                 else "",
                  })

    def percent(self, key):
        return (float(self[key]) / float(self["total"])) * 100


class AudioStat(Stat):
    def compute(self, audio_file):
        assert(audio_file)
        self["total"] += 1
        self._compute(audio_file)

    def _compute(self, audio_file):
        pass


class FileCounterStat(Stat):
    def __init__(self):
        super(FileCounterStat, self).__init__()
        for k in ("audio", "hidden", "audio (other)"):
            self[k] = 0

    def _compute(self, file, audio_file):
        if audio_file:
            self["audio"] += 1
        if os.path.basename(file).startswith('.'):
            self["hidden"] += 1
        mt = guessMimetype(file)
        if mt and mt.startswith("audio/") and not audio_file:
            self["unsupported (other)"] += 1

    def _report(self):
        print(cli.BOLD + cli.GREY + "Files:" + cli.RESET)
        super(FileCounterStat, self)._report()


class MimeTypeStat(Stat):
    def _compute(self, file, audio_file):
        mt = guessMimetype(file)
        self[mt] += 1

    def _report(self):
        print(cli.BOLD + cli.GREY + "Mime-Types:" + cli.RESET)
        super(MimeTypeStat, self)._report(most_common=True)


class Id3VersionCounter(AudioStat):
    def __init__(self):
        super(Id3VersionCounter, self).__init__()
        for v in ID3_VERSIONS:
            self[v] = 0
            self._key_names[v] = id3.versionToString(v)

    def _compute(self, audio_file):
        if audio_file.tag:
            self[audio_file.tag.version] += 1
        else:
            self[None] += 1

    def _report(self):
        print(cli.BOLD + cli.GREY + "ID3 versions:" + cli.RESET)
        super(Id3VersionCounter, self)._report()


class Id3FrameCounter(AudioStat):
    def _compute(self, audio_file):
        if audio_file.tag:
            for frame_id in audio_file.tag.frame_set:
                self[frame_id] += len(audio_file.tag.frame_set[frame_id])

    def _report(self):
        print(cli.BOLD + cli.GREY + "ID3 frames:" + cli.RESET)
        super(Id3FrameCounter, self)._report(most_common=True)


class BitrateCounter(AudioStat):
    def __init__(self):
        super(BitrateCounter, self).__init__()
        self["cbr"] = 0
        self["vbr"] = 0
        self.bitrate_keys = [(operator.le, 96),
                             (operator.le, 112),
                             (operator.le, 128),
                             (operator.le, 160),
                             (operator.le, 192),
                             (operator.le, 256),
                             (operator.le, 320),
                             (operator.gt, 320),
                            ]
        for k in self.bitrate_keys:
            self[k] = 0
            op, bitrate = k
            self._key_names[k] = "%s %d" % (_OP_STRINGS[op], bitrate)

    def _compute(self, audio_file):
        if audio_file.type != AUDIO_MP3 or audio_file.info is None:
            self["total"] -=1
            return

        vbr, br =  audio_file.info.bit_rate
        if vbr:
            self["vbr"] += 1
        else:
            self["cbr"] += 1

        for key in self.bitrate_keys:
            key_op, key_br = key
            if key_op(br, key_br):
                self[key] += 1
                break

    def _report(self):
        print(cli.BOLD + cli.GREY + "MP3 bitrates:" + cli.RESET)
        super(BitrateCounter, self)._report(most_common=True)

    def _sortedKeys(self, most_common=False):
        keys = super(BitrateCounter, self)._sortedKeys(most_common=most_common)
        keys.remove("cbr")
        keys.remove("vbr")
        keys.insert(0, "cbr")
        keys.insert(1, "vbr")
        return keys


class RuleViolationStat(Stat):
    def _report(self):
        print(cli.BOLD + cli.GREY + "Rule Violations:" + cli.RESET)
        super(RuleViolationStat, self)._report(most_common=True)


class StatisticsPlugin(LoaderPlugin):
    NAMES = ['stats']
    SUMMARY = u"Computes statistics for all audio files scanned."

    def __init__(self, arg_parser):
        super(StatisticsPlugin, self).__init__(arg_parser)

        self.arg_group.add_argument(
                "--verbose", action="store_true", default=False,
                help="Show details for each file with rule violations.")

        self._stats = []
        self._rules_stat = RuleViolationStat()

        self._stats.append(FileCounterStat())
        self._stats.append(MimeTypeStat())
        self._stats.append(Id3VersionCounter())
        self._stats.append(Id3FrameCounter())
        self._stats.append(BitrateCounter())
        self._stats.append(self._rules_stat)

        self._score_sum = 0
        self._score_count = 0
        self._rules_log = {}
        self._rules = [ Id3TagRules(),
                        FileRule(),
                        ArtworkRule(),
                        BitrateRule(),
                        Id3FrameRules(),
                      ]

    def handleFile(self, path):
        super(StatisticsPlugin, self).handleFile(path)
        sys.stdout.write('.')
        sys.stdout.flush()

        for stat in self._stats:
            if isinstance(stat, AudioStat):
                if self.audio_file:
                    stat.compute(self.audio_file)
            else:
                stat.compute(path, self.audio_file)

        self._score_count += 1
        total_score = 100
        for rule in self._rules:
            scores = rule.test(path, self.audio_file) or []
            if scores:
                if path not in self._rules_log:
                    self._rules_log[path] = []

                for score, text in scores:
                    self._rules_stat[text] += 1
                    self._rules_log[path].append((score, text))
                    # += because negative values are returned
                    total_score += score

        self._score_sum += total_score

    def handleDone(self):
        print()
        for stat in self._stats:
            stat.report()
            print()

        # Detailed rule violations
        if self.args.verbose:
            for path in self._rules_log:
                print(path)
                for score, text in self._rules_log[path]:
                    print("\t%s%s%s (%s)" % (cli.RED, str(score).center(3),
                                             cli.RESET, text))

        def prettyScore():
            score = float(self._score_sum) / float(self._score_count)
            if score > 80:
                color = cli.GREEN
            elif score > 70:
                color = cli.YELLOW
            else:
                color = cli.RED
            return (score, color)

        score, color = prettyScore()
        print("%sScore%s = %s%d%%%s" % (cli.BOLD, cli.BOLD_OFF,
                                        color, score, cli.RESET))
        if not self.args.verbose:
            print("Run with --verbose to see files and their rule violations")
        print()



