from functools import singledispatch

from examples.lisp.constructs import Function, Form, Atom, builtin_functions
from examples.lisp.type_system.types import PrimitiveType, UnrecognizedType, EmptyList, ListType, PossibleEmptyList


def is_string_literal(atom: Atom) -> bool:
    return atom.value == "\"\"" or (atom.value.startswith("\"") and atom.value.endswith("\""))


def is_bool_literal(atom: Atom):
    return atom.value == "true" or atom.value == "false"


def is_numeric_literal(atom: Atom):
    return isinstance(atom.value, int) or isinstance(atom.value, float)


def is_empty_list(t):
    return isinstance(t, EmptyList)


def is_list(t):
    return isinstance(t, ListType)


def is_possibly_empty(t2):
    return isinstance(t2, PossibleEmptyList)


def infer_element_types(list1, list2) -> tuple[bool, object]:
    def inner(t1, t2) -> tuple[bool, object]:
        if is_list(t1) and is_list(t2):
            result, element_type = infer_element_types(t1.element, t2.element)
            if not result:
                return False, f"Incompatible list types '{t1.name()}', '{t2.name()}'"
            return True, ListType(element=element_type)


        if is_list(t1) and is_empty_list(t2):
            return True, PossibleEmptyList(element=t1.element)

        if is_list(t1) and is_possibly_empty(t2):
            result, element_type = infer_element_types(t1.element, t2.element)
            if not result:
                return False, f"Incompatible list types '{t1.name()}', '{t2.name()}'"
            return True, PossibleEmptyList(element=t1.element)

        return False, ""

    result, list_type = inner(list2, list1)
    if not result:
        result, list_type = inner(list1, list2)
        if not result:
            if list1 == list2:
                return True, list1
            return False, f"Incompatible list types '{list1.name()}', '{list2.name()}'"

    return True, list_type


@singledispatch
def infer_type(obj, namespace: dict[str, object]) -> tuple[bool, dict[object]]:
    raise TypeError(f"Cannot infer type of {obj}")


@infer_type.register
def _(atom: Atom, namespace: dict[str, object]) -> tuple[bool, PrimitiveType | UnrecognizedType]:
    if isinstance(atom.value, str):
        if is_string_literal(atom):
            return True, PrimitiveType.String
        if is_bool_literal(atom):
            return True, PrimitiveType.Bool
        if atom.value in namespace:
            return True, namespace[atom.value]

        try:
            float(atom.value)
            return True, PrimitiveType.Number
        except:
            try:
                int(atom.value)
                return True, PrimitiveType.Number
            except:
                return False, f"Cannot infer type of '{atom.value}'"

    if is_numeric_literal(atom):
        return True, PrimitiveType.Number
    return False, UnrecognizedType()


@infer_type.register
def _(form: Form, namespace: dict[str, object]) -> tuple[bool, object]:
    elements = form.elements
    first_element = elements[0]
    if isinstance(first_element, Atom):
        name = first_element.value
        if name in namespace:
            return True, namespace[name]
        elif name in builtin_functions():
            match name:
                case "list":
                    if len(elements) == 1:
                        return True, EmptyList()

                    result, element_type = infer_type(elements[1], namespace)
                    if not result:
                        return False, element_type

                    for i in range(2, len(elements)):
                        result, i_type = infer_type(elements[i], namespace)
                        if not result:
                            return False, i_type

                        result, resulting_list_type = infer_element_types(ListType(element=element_type), ListType(element=i_type))
                        if not result:
                            #todo: save all valid i_type in a set (+ first element_type) and add them to this error message
                            return False, f"List {i - 1}-th element has type '{i_type.name()}' which is not compatible with inferred type '{element_type.name()}'"

                        element_type = resulting_list_type.element

                    return True, ListType(element_type)

                case "++":
                    result_element, element_type = infer_type(elements[1], namespace)
                    result_list, list_type = infer_type(elements[2], namespace)

                    if not result_element:
                        return False, element_type

                    if not result_list:
                        return False, list_type

                    if is_empty_list(list_type):
                        return True, ListType(element_type)

                    if is_list(list_type) or is_possibly_empty(list_type):
                        result, resulting_list_type = infer_element_types(ListType(element=element_type), list_type)
                        if result:
                            return True, resulting_list_type

                    return False, f"Cannot append element of type '{element_type.name()}' to '{list_type.name()}'"

                case "first":
                    result, list_type = infer_type(elements[1], namespace)
                    if not result:
                        return False, list_type

                    if is_list(list_type):
                        return True, list_type.element

                    return False, f"'first' expected a non-empty List type but got '{list_type.name()}'"

                case "rest":
                    result, list_type = infer_type(elements[1], namespace)
                    if not result:
                        return False, list_type

                    if is_list(list_type):
                        return True, PossibleEmptyList(element=list_type.element)

                    return False, f"'rest' expected a non-empty List type but got '{list_type.name()}'"

                case "if":
                    result_condition, condition_type = infer_type(elements[1], namespace)
                    if not result_condition:
                        return False, condition_type

                    if condition_type != PrimitiveType.Bool:
                        return False, f"Expected if condition to have type 'bool' but got '{condition_type.name()}'"

                    result_true_branch, true_branch_type = infer_type(elements[2], namespace)
                    if not result_true_branch:
                        return False, true_branch_type

                    result_false_branch, false_branch_type = infer_type(elements[3], namespace)
                    if not result_false_branch:
                        return False, false_branch_type

                    if true_branch_type != false_branch_type:
                        maybe_empty_predicate = (lambda t1, t2: is_list(t1) and
                                                                (is_empty_list(t2) or is_possibly_empty(t2)))
                        possible_empty_list = (maybe_empty_predicate(true_branch_type, false_branch_type)
                                               or maybe_empty_predicate(false_branch_type, true_branch_type))
                        if possible_empty_list:
                            return True, PossibleEmptyList(true_branch_type.element if isinstance(true_branch_type,
                                                                                                  ListType) else false_branch_type.element)

                        return False, f"Incompatible types in if branches: '{true_branch_type.name()}' and '{false_branch_type.name()}'"

                    return True, true_branch_type

        return False, f"Unrecognized form '{name}', cannot infer type"
