#include "compare_engine.h"
#include <algorithm>
#include <cmath>
#include <unordered_map>
#include <sstream>

namespace pdfdiff {

static bool is_space(char32_t c) {
    return c == ' ' || c == '\t' || c == '\u00A0' || c == '\u2009';
}

static bool is_newline(char32_t c) {
    return c == '\n' || c == '\r' || c == 0x2028 || c == 0x2029;
}

static char32_t to_lower(char32_t c) {
    if (c >= 'A' && c <= 'Z') return c + 32;
    // Korean / other: keep as-is for now (full Unicode lower can be added)
    return c;
}

std::vector<Glyph> Normalizer::normalize(
    const std::vector<Glyph>& raw,
    const ComparisonOptions& opts,
    bool page_aware)
{
    if (raw.empty()) return {};

    // For Body mode we keep a simpler path close to the original Python logic
    if (opts.mode == ComparisonOptions::Mode::Body) {
        std::vector<Glyph> result;
        int word_id = 0;
        float last_y = -1e9f;
        int last_page = -1;

        for (const auto& g : raw) {
            if (page_aware && (g.page != last_page || std::abs(g.y - last_y) > 5.0f)) {
                word_id++;
                last_page = g.page;
            } else if (!page_aware && std::abs(g.y - last_y) > 5.0f) {
                word_id++;
            }
            last_y = g.y;

            // Basic filtering similar to original body mode
            std::string clean = g.ch;
            // strip + lower
            std::string filtered;
            for (unsigned char c : clean) {
                if (std::isalnum(c) || std::string(".,?!;:()-[]{}'\"").find(c) != std::string::npos)
                    filtered += std::tolower(c);
            }
            if (filtered.empty()) continue;

            Glyph out = g;
            out.ch = filtered;
            out.word_id = word_id;
            result.push_back(out);
        }
        return result;
    }

    // Strict / Custom path (simplified skeleton – extend as needed)
    std::vector<Glyph> result;
    int word_id = 0;

    for (size_t i = 0; i < raw.size(); ++i) {
        const auto& g = raw[i];
        std::string src = g.source_ch.empty() ? g.ch : g.source_ch;

        for (char c : src) {
            char32_t cp = static_cast<unsigned char>(c); // TODO: proper UTF-8

            if (is_newline(cp) && opts.ignore_line_breaks) continue;
            if (is_space(cp) && !is_newline(cp) && opts.ignore_spaces) continue;
            // symbol filter can be added here

            Glyph out = g;
            out.ch = std::string(1, static_cast<char>(opts.ignore_case ? to_lower(cp) : cp));
            out.source_ch = std::string(1, c);
            out.word_id = word_id;
            result.push_back(out);
        }
        word_id++;
    }
    return result;
}

} // namespace pdfdiff
