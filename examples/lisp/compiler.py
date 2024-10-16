import logging
from functools import singledispatch

from itertools import islice

from examples.lisp.constructs import Form, builtin_functions, to_object, is_function_def, is_import, to_function, \
    Function, Atom
from examples.lisp.type_system.type_checker import check_types, infer_type
from parser.ast import AST

logger = logging.getLogger("laxma.compiler")


@singledispatch
def compile_obj(obj, indent: int = 0):
    raise TypeError(f"Could not compile object {obj}")


@compile_obj.register
def _(obj: Atom, indent: int = 0):
    current_indent = ' ' * (indent * 4)
    value = obj.value
    if obj.value == 'true' or obj.value == 'false':
        value = obj.value.capitalize()
    return f"{current_indent}{value}"


@compile_obj.register
def _(obj: Form, indent: int = 0):
    current_indent = ' ' * (indent * 4)
    builtins = builtin_functions()

    if not obj.elements:
        return ""
    if not isinstance(obj.elements[0], Atom):
        raise SyntaxError(f"Expected Atom as first element of Form, but got {obj.elements[0]}")

    form_name = obj.elements[0].value
    if form_name in builtins:
        return f"{current_indent}{compile_builtin(obj)}"
    else:
        args = ','.join([compile_obj(element) for element in islice(obj.elements, 1, len(obj.elements))])
        return f"{current_indent}{form_name}({args})"


def compile_builtin(form: Form):
    function_name = form.elements[0].value

    def create_body(delim: str, elements: islice | list = islice(form.elements, 1, len(form.elements))):
        return delim.join([compile_obj(element) for element in elements])

    def create_op(op: str, form: Form, n_args: int = 2):
        args = len(form.elements) - 1
        if args != n_args:
            raise TypeError(f"'{op}' takes {n_args} arguments but {args} were given!")
        return create_body(f' {op} ')

    match function_name:
        case "import":
            return f"import {form.elements[1].value}"
        case "print":
            return f"print({create_body(', ')})"
        case "+":
            return create_body(' + ')
        case "-":
            return create_body(' - ')
        case "*":
            return create_body(' * ')
        case "/":
            return create_body(' / ')
        case "not":
            n_args = len(form.elements) - 1
            if n_args != 1:
                raise TypeError(f"'not' takes 1 argument but {n_args} were given!")
            return ' not ' + create_body('')
        case "and" | "or":
            return create_body(f' {function_name} ')
        case "<" | ">" | "<=" | ">=":
            return create_op(function_name, form)
        case "=":
            n_args = len(form.elements) - 1
            if n_args != 2:
                raise TypeError(f"'=' takes 2 arguments but {n_args} were given!")
            return create_body(' == ')
        case "list":
            return f"list_create({create_body(', ')})"
        case "first":
            n_args = len(form.elements) - 1
            if n_args != 1:
                raise TypeError(f"'first' takes 1 argument but {n_args} were given!")
            return f"{create_body('')}[0]"
        case "rest":
            n_args = len(form.elements) - 1
            if n_args != 1:
                raise TypeError(f"'rest' takes 1 argument but {n_args} were given!")
            return f"{create_body('')}[1:]"
        case "++":
            return f"list_append({create_body(', ')})"
        case "map":
            n_args = len(form.elements) - 1
            if n_args != 2:
                raise TypeError(f"'map' takes 2 arguments but {n_args} were given!")

            func = compile_obj(form.elements[1])
            collection = compile_obj(form.elements[2])
            return f"list(map({func}, {collection}))"
        case "filter":
            n_args = len(form.elements) - 1
            if n_args != 2:
                raise TypeError(f"'filter' takes 2 arguments but {n_args} were given!")

            func = compile_obj(form.elements[1])
            collection = compile_obj(form.elements[2])
            return f"list(filter({func}, {collection}))"
        case "lambda":
            args = form.elements[1]
            if isinstance(args, Atom):
                args = compile_obj(args)
            elif isinstance(args, Form):
                args = create_body(', ', args.elements)
            else:
                raise TypeError(f"Expected Form or Atom but got {type(args)}")
            return f"lambda {args}: {compile_obj(form.elements[2])}"
        case "if":
            n_args = len(form.elements) - 1
            if n_args != 3:
                raise TypeError(f"if requires 3 arguments but {n_args} were given!")

            condition = compile_obj(form.elements[1])
            if_branch = compile_obj(form.elements[2])
            else_branch = compile_obj(form.elements[3])
            return f"({if_branch}) if ({condition}) else ({else_branch})"
    return ""


def compile_function(function: Function, indent: int):
    builtins = builtin_functions()
    if function.name in builtins:
        logger.error(f"Error: builtin function {function.name} is being redefined.")

    def create_body(add_return: bool):
        return_f = lambda i: 'return ' if add_return and i == len(function.body) - 1 else ''
        total_indent = ' ' * (indent + 1) * 4
        body = [f"{total_indent}{return_f(i)}{compile_obj(obj, indent)}" for i, obj in enumerate(function.body)]
        return '\n'.join(body)

    if function.name == "main":
        output = f"if __name__ == '__main__':\n{create_body(False)}\n"
    else:
        output = f"def {function.name}({', '.join(function.args)}):\n{create_body(True)}"

    return output + "\n"


def validate(objects) -> tuple[bool, str]:
    for obj in objects:
        if not isinstance(obj, Form):
            return False, f"Got unexpected object at root-level: {obj}"
        if not is_function_def(obj) and is_import(obj):
            return False, f"Expected only function definitions and imports at root-level but got: {obj}"
    return True, ""


def compile_program(ast: AST, ext_funcs: dict[str, Function] = None, is_repl: bool = False) -> tuple[bool, str, dict]:
    if ext_funcs is None:
        ext_funcs = {}

    if not ast.children:
        return True, "", {}

    objects = [to_object(child) for child in ast.children]

    validation_result, validation_message = validate(objects)
    if not validation_result:
        return False, validation_message, {}

    namespace = {
        **ext_funcs,
        **{form.elements[1].value: to_function(form) for form in objects if is_function_def(form)},
    }

    if not is_repl and 'main' not in namespace:
        return False, f"Function 'main' is not defined!", {}

    output = convert_to_output(is_repl, namespace, objects)
    return True, output, namespace


def convert_to_output(is_repl, namespace, objects):
    output = "from lisp_core import *\n\n"
    for function in namespace.values():
        output += compile_function(function, 0) + "\n"
    if is_repl:
        output += "\n".join([compile_obj(form) for form in objects if not is_function_def(form)]) + "\n\n"
    return output
