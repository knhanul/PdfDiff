#include "compare_engine.h"
#include <algorithm>

namespace pdfdiff {

// Simple LCS-based diff (good enough for skeleton; replace with Myers later if needed)
std::vector<DiffOp> Comparator::diff(
    const std::vector<Glyph>& a,
    const std::vector<Glyph>& b)
{
    const int n = static_cast<int>(a.size());
    const int m = static_cast<int>(b.size());

    // DP table (memory can be optimized later)
    std::vector<std::vector<int>> dp(n + 1, std::vector<int>(m + 1, 0));
    for (int i = 1; i <= n; ++i)
        for (int j = 1; j <= m; ++j)
            if (a[i-1].ch == b[j-1].ch)
                dp[i][j] = dp[i-1][j-1] + 1;
            else
                dp[i][j] = std::max(dp[i-1][j], dp[i][j-1]);

    std::vector<DiffOp> ops;
    int i = n, j = m;
    while (i > 0 || j > 0) {
        if (i > 0 && j > 0 && a[i-1].ch == b[j-1].ch) {
            ops.push_back({DiffOp::Type::Equal, i-1, i, j-1, j});
            --i; --j;
        } else if (j > 0 && (i == 0 || dp[i][j-1] >= dp[i-1][j])) {
            ops.push_back({DiffOp::Type::Insert, i, i, j-1, j});
            --j;
        } else {
            ops.push_back({DiffOp::Type::Delete, i-1, i, j, j});
            --i;
        }
    }
    std::reverse(ops.begin(), ops.end());
    return ops;
}

} // namespace pdfdiff
