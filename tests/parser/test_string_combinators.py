from parser.ast import AST
from parser.string_combinators import match_str, match_regex
from parser.token_stream import TokenStream
from parser.types import ParserResult


def test_str():
    parser = match_str("FOR-LOOP", "for")

    assert (parser(TokenStream(["for"])) ==
            ParserResult.succeeded(AST("FOR-LOOP", ["for"], None), TokenStream(["for"]).advance()[1]))
    assert (parser(TokenStream(["for", "a"])) ==
            ParserResult.succeeded(AST("FOR-LOOP", ["for"], None), TokenStream(["for", "a"]).advance()[1]))
    assert parser(TokenStream(["for2"])) == ParserResult.failed(TokenStream(["for2"]))


def test_regex():
    parser = match_regex("FOR-LOOP", "for$")

    assert (parser(TokenStream(["for"])) ==
            ParserResult.succeeded(AST("FOR-LOOP", ["for"], None), TokenStream(["for"]).advance()[1]))
    assert parser(TokenStream(["for2"])) == ParserResult.failed(TokenStream(["for2"]))
