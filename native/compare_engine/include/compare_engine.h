#pragma once

#include <string>
#include <vector>
#include <optional>
#include <cstdint>

namespace pdfdiff {

struct Glyph {
    std::string ch;           // normalized character
    std::string source_ch;    // original
    float x = 0.f, y = 0.f;
    float bbox[4] = {0,0,0,0}; // x0,y0,x1,y1
    int page = 0;
    int word_id = 0;
    bool synthetic = false;
};

struct ComparisonOptions {
    enum class Mode { Body, Strict, Custom };
    Mode mode = Mode::Body;

    bool ignore_spaces = true;
    bool ignore_line_breaks = true;
    bool ignore_case = true;
    bool ignore_symbols = false;
};

struct DiffOp {
    enum class Type { Equal, Insert, Delete, Replace };
    Type type;
    int a_start = 0, a_end = 0;
    int b_start = 0, b_end = 0;
};

class Normalizer {
public:
    // Convert raw character list (from PyMuPDF style dict) into normalized glyphs
    static std::vector<Glyph> normalize(
        const std::vector<Glyph>& raw,
        const ComparisonOptions& opts,
        bool page_aware = true
    );
};

class Comparator {
public:
    // Simple sequence diff on normalized glyph characters
    static std::vector<DiffOp> diff(
        const std::vector<Glyph>& a,
        const std::vector<Glyph>& b
    );
};

} // namespace pdfdiff
