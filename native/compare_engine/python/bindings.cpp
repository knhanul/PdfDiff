#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include "compare_engine.h"

namespace py = pybind11;
using namespace pdfdiff;

PYBIND11_MODULE(compare_engine, m) {
    m.doc() = "PdfDiff comparison engine (C++)";

    py::class_<Glyph>(m, "Glyph")
        .def(py::init<>())
        .def_readwrite("ch", &Glyph::ch)
        .def_readwrite("source_ch", &Glyph::source_ch)
        .def_readwrite("x", &Glyph::x)
        .def_readwrite("y", &Glyph::y)
        .def_readwrite("page", &Glyph::page)
        .def_readwrite("word_id", &Glyph::word_id)
        .def_readwrite("synthetic", &Glyph::synthetic);

    py::class_<ComparisonOptions>(m, "ComparisonOptions")
        .def(py::init<>())
        .def_readwrite("ignore_spaces", &ComparisonOptions::ignore_spaces)
        .def_readwrite("ignore_line_breaks", &ComparisonOptions::ignore_line_breaks)
        .def_readwrite("ignore_case", &ComparisonOptions::ignore_case)
        .def_readwrite("ignore_symbols", &ComparisonOptions::ignore_symbols);

    py::enum_<ComparisonOptions::Mode>(m, "Mode")
        .value("Body", ComparisonOptions::Mode::Body)
        .value("Strict", ComparisonOptions::Mode::Strict)
        .value("Custom", ComparisonOptions::Mode::Custom);

    py::enum_<DiffOp::Type>(m, "DiffType")
        .value("Equal", DiffOp::Type::Equal)
        .value("Insert", DiffOp::Type::Insert)
        .value("Delete", DiffOp::Type::Delete)
        .value("Replace", DiffOp::Type::Replace);

    py::class_<DiffOp>(m, "DiffOp")
        .def_readonly("type", &DiffOp::type)
        .def_readonly("a_start", &DiffOp::a_start)
        .def_readonly("a_end", &DiffOp::a_end)
        .def_readonly("b_start", &DiffOp::b_start)
        .def_readonly("b_end", &DiffOp::b_end);

    m.def("normalize", &Normalizer::normalize,
          py::arg("raw"), py::arg("opts"), py::arg("page_aware") = true);

    m.def("diff", &Comparator::diff);
}
