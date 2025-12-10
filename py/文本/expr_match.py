# 复杂表达式匹配，50个词以下性能好
import re
from collections import Counter
from functools import lru_cache
import ply.lex as lex
import ply.yacc as yacc
import threading

# 全局缓存解析器
_parser_cache = None
_lexer_cache = None

# 缓存版本控制
_cache_version = 0
_cache_lock = threading.Lock()


def invalidate_cache():
    """
    当关键词组变化时调用此函数清空所有缓存
    """
    global _cache_version
    with _cache_lock:
        _cache_version += 1
        _find_keywords_simple_cached.cache_clear()
        _find_keywords_regex_cached.cache_clear()
        _complex_expression_cached.cache_clear()
        print(f"✓ Cache cleared, new version: {_cache_version}")


def get_cache_info():
    """
    获取缓存统计信息（可选，用于监控）
    """
    return {
        'version': _cache_version,
        'simple_cache': _find_keywords_simple_cached.cache_info(),
        'regex_cache': _find_keywords_regex_cached.cache_info(),
        'expression_cache': _complex_expression_cached.cache_info()
    }


def _get_parser():
    """获取缓存的解析器"""
    global _parser_cache, _lexer_cache

    if _parser_cache is not None and _lexer_cache is not None:
        return _parser_cache, _lexer_cache

    tokens = ('LPAREN', 'RPAREN', 'OR', 'AND', 'WORD')

    t_LPAREN = r'\('
    t_RPAREN = r'\)'
    t_OR = r'\|'
    t_AND = r'\+'
    t_WORD = r'[^\(\)\+\|\s]+'
    t_ignore = ' \t\n'

    def t_error(t):
        print("Illegal character '%s'" % t.value[0])
        t.lexer.skip(1)

    lexer = lex.lex()

    # ============ 修复后的语法规则 ============

    def p_expression_and(p):
        '''expression : expression AND term'''
        # AND操作：创建嵌套结构表示"必须同时满足"
        if isinstance(p[1], list) and len(p[1]) > 0 and isinstance(p[1][0], list):
            # 已经是AND结构，继续追加
            p[0] = p[1] + [p[3]]
        else:
            # 创建新的AND结构
            p[0] = [p[1], p[3]]

    def p_expression_term(p):
        '''expression : term'''
        p[0] = p[1]

    def p_term_or(p):
        '''term : term OR factor'''
        # OR操作：平铺列表
        if isinstance(p[1], list) and not any(isinstance(x, list) for x in p[1]):
            # 已经是OR列表，继续追加
            p[0] = p[1] + [p[3]] if isinstance(p[3], str) else p[1] + p[3]
        else:
            # 创建新的OR列表
            p[0] = [p[1], p[3]] if isinstance(p[3], str) else [p[1]] + p[3]

    def p_term_factor(p):
        '''term : factor'''
        p[0] = p[1]

    def p_factor_group(p):
        '''factor : LPAREN expression RPAREN'''
        # 括号内的表达式直接返回，保持结构
        p[0] = p[2]

    def p_factor_word(p):
        '''factor : WORD'''
        p[0] = p[1]

    def p_error(p):
        if p:
            raise SyntaxError(f"Syntax error at '{p.value}'")
        else:
            raise SyntaxError("Syntax error at EOF")

    parser = yacc.yacc(debug=False, write_tables=False)

    _parser_cache = parser
    _lexer_cache = lexer

    return parser, lexer


# ============ 内部缓存函数（带版本号） ============

@lru_cache(maxsize=2048)
def _find_keywords_simple_cached(text_lower, keywords_tuple, cache_ver):
    """内部缓存函数 - 简单关键词查找"""
    word_counts = {}

    for keyword in keywords_tuple:
        keyword_lower = keyword.lower()
        count = text_lower.count(keyword_lower)
        if count > 0:
            word_counts[keyword_lower] = count

    return word_counts


@lru_cache(maxsize=1024)
def _find_keywords_regex_cached(text_lower, keywords_tuple, cache_ver):
    """内部缓存函数 - 正则表达式查找"""
    if not keywords_tuple:
        return {}

    escaped_keywords = [re.escape(k.lower()) for k in keywords_tuple]
    pattern = '|'.join(f'({k})' for k in escaped_keywords)

    matches = re.findall(pattern, text_lower)
    flat_matches = [m for group in matches for m in group if m]

    return dict(Counter(flat_matches))


@lru_cache(maxsize=512)
def _complex_expression_cached(expression, cache_ver):
    """内部缓存函数 - 复杂表达式解析"""
    parser, lexer = _get_parser()

    try:
        result = parser.parse(expression, lexer=lexer)
        return result
    except SyntaxError as e:
        print(e)
        return None


# ============ 对外接口（与原始代码完全一致） ============

def find_keywords_simple(text, keywords):
    """
    简单关键词查找 - 自动使用缓存
    与原始代码接口完全一致
    """
    global _cache_version

    text_lower = text.lower()
    keywords_tuple = tuple(sorted(keywords))  # 转为可哈希类型

    # 自动查询缓存，不存在则生成
    return _find_keywords_simple_cached(text_lower, keywords_tuple, _cache_version)


def find_keywords_regex(text, keywords):
    """
    正则表达式查找 - 自动使用缓存
    与原始代码接口完全一致
    """
    global _cache_version

    if not keywords:
        return {}

    text_lower = text.lower()
    keywords_tuple = tuple(sorted(keywords))

    # 自动查询缓存，不存在则生成
    return _find_keywords_regex_cached(text_lower, keywords_tuple, _cache_version)


def complex_expression(expr):
    """
    重写的表达式解析器 - 使用递归下降解析
    
    语法规则:
    expression := or_expr
    or_expr    := and_expr ('|' and_expr)*
    and_expr   := term ('+' term)*
    term       := '(' expression ')' | keyword
    
    返回结构:
    - 字符串: 单个关键词
    - {'op': 'OR', 'items': [...]}:  OR表达式
    - {'op': 'AND', 'items': [...]}: AND表达式
    """
    
    class Parser:
        def __init__(self, expr):
            self.expr = expr.replace(' ', '')
            self.pos = 0
            self.length = len(self.expr)
        
        def peek(self):
            """查看当前字符"""
            if self.pos < self.length:
                return self.expr[self.pos]
            return None
        
        def consume(self):
            """消费当前字符"""
            if self.pos < self.length:
                char = self.expr[self.pos]
                self.pos += 1
                return char
            return None
        
        def parse_keyword(self):
            """解析关键词"""
            start = self.pos
            while self.pos < self.length and self.expr[self.pos] not in '()|+':
                self.pos += 1
            return self.expr[start:self.pos]
        
        def parse_term(self):
            """解析term: '(' expression ')' | keyword"""
            if self.peek() == '(':
                self.consume()  # 消费 '('
                result = self.parse_or_expr()
                if self.peek() == ')':
                    self.consume()  # 消费 ')'
                return result
            else:
                return self.parse_keyword()
        
        def parse_and_expr(self):
            """解析AND表达式: term ('+' term)*"""
            items = [self.parse_term()]
            
            while self.peek() == '+':
                self.consume()  # 消费 '+'
                items.append(self.parse_term())
            
            if len(items) == 1:
                return items[0]
            return {'op': 'AND', 'items': items}
        
        def parse_or_expr(self):
            """解析OR表达式: and_expr ('|' and_expr)*"""
            items = [self.parse_and_expr()]
            
            while self.peek() == '|':
                self.consume()  # 消费 '|'
                items.append(self.parse_and_expr())
            
            if len(items) == 1:
                return items[0]
            return {'op': 'OR', 'items': items}
        
        def parse(self):
            """入口函数"""
            return self.parse_or_expr()
    
    parser = Parser(expr)
    return parser.parse()


def expr_match(expr, value):
    """
    表达式匹配 - 使用新的解析器
    """
    # 清理表达式
    expr = re.sub(r'\s+', '', expr)
    keywords = set(re.findall(r'[^\(\)\+\|]+', expr))

    if not keywords:
        return False

    value_lower = value.lower()

    # 查找关键词
    if len(keywords) <= 20:
        target_list = find_keywords_simple(value_lower, keywords)
    else:
        target_list = find_keywords_regex(value_lower, keywords)

    if not target_list:
        return False

    target_set = set(target_list.keys())

    # 快速路径1：简单AND表达式（a+b+c）
    if '+' in expr and '|' not in expr and '(' not in expr:
        keywords_lower = {k.lower() for k in keywords}
        if keywords_lower.issubset(target_set):
            return target_list
        return False

    # 快速路径2：简单OR表达式（a|b|c）
    if '|' in expr and '+' not in expr and '(' not in expr:
        keywords_lower = {k.lower() for k in keywords}
        if keywords_lower.intersection(target_set):
            return target_list
        return False

    # 复杂表达式
    try:
        parsed_result = complex_expression(expr)
        if _check_match(parsed_result, target_set):
            return target_list
    except Exception as e:
        # 解析失败，回退到旧逻辑
        print(f"解析失败: {expr}, 错误: {e}")
        return False

    return False


def _check_match(parsed_result, target_set):
    """
    递归检查解析结果是否匹配
    
    参数:
    - parsed_result: 解析结果（字符串或字典）
    - target_set: 文本中找到的关键词集合（小写）
    
    返回: True/False
    """
    if not parsed_result:
        return False
    
    # 情况1: 字符串 - 单个关键词
    if isinstance(parsed_result, str):
        return parsed_result.lower() in target_set
    
    # 情况2: 字典 - 复合表达式
    if isinstance(parsed_result, dict):
        op = parsed_result.get('op')
        items = parsed_result.get('items', [])
        
        if not items:
            return False
        
        if op == 'OR':
            # OR: 任一子项满足即可
            return any(_check_match(item, target_set) for item in items)
        
        elif op == 'AND':
            # AND: 所有子项必须满足
            return all(_check_match(item, target_set) for item in items)
    
    return False


# ============ 使用示例 ============

if __name__ == "__main__":

    print("\n" * 2)
    print("=" * 80)
    print("简单规则测试")
    print("=" * 80)

    # 测试1: 单个关键词
    print("\n【测试1】单个关键词匹配")
    print("规则: airbus")
    test_cases_1 = [
        ("Airbus announces new aircraft", True, "匹配：airbus"),
        ("Boeing 737 update", False, "不匹配：无airbus"),
        ("AIRBUS A320 safety", True, "匹配：大写AIRBUS"),
        ("The airbus fleet", True, "匹配：小写airbus"),
    ]
    for text, expected, desc in test_cases_1:
        result = expr_match("airbus", text)
        status = "✓" if bool(result) == expected else "✗"
        print(f"  {status} {desc}")
        print(f"    文本: {text}")
        print(f"    结果: {result}")

    # 测试2: 两个关键词OR
    print("\n【测试2】两个关键词OR")
    print("规则: airbus|boeing")
    test_cases_2 = [
        ("Airbus A320 report", True, "匹配：airbus"),
        ("Boeing 737 update", True, "匹配：boeing"),
        ("Airbus and Boeing comparison", True, "匹配：airbus和boeing都有"),
        ("Embraer aircraft news", False, "不匹配：无airbus或boeing"),
    ]
    for text, expected, desc in test_cases_2:
        result = expr_match("airbus|boeing", text)
        status = "✓" if bool(result) == expected else "✗"
        print(f"  {status} {desc}")
        print(f"    文本: {text}")
        print(f"    结果: {result}")

    # 测试3: 两个关键词AND
    print("\n【测试3】两个关键词AND")
    print("规则: airbus+a320")
    test_cases_3 = [
        ("Airbus A320 safety report", True, "匹配：airbus和a320都有"),
        ("Airbus A350 update", False, "不匹配：有airbus但无a320"),
        ("A320 aircraft details", False, "不匹配：有a320但无airbus"),
        ("Boeing 737 news", False, "不匹配：两个都没有"),
    ]
    for text, expected, desc in test_cases_3:
        result = expr_match("airbus+a320", text)
        status = "✓" if bool(result) == expected else "✗"
        print(f"  {status} {desc}")
        print(f"    文本: {text}")
        print(f"    结果: {result}")

    # 测试4: 三个关键词OR
    print("\n【测试4】三个关键词OR")
    print("规则: airbus|boeing|embraer")
    test_cases_4 = [
        ("Airbus news", True, "匹配：airbus"),
        ("Boeing update", True, "匹配：boeing"),
        ("Embraer aircraft", True, "匹配：embraer"),
        ("Bombardier jet", False, "不匹配：无任何关键词"),
    ]
    for text, expected, desc in test_cases_4:
        result = expr_match("airbus|boeing|embraer", text)
        status = "✓" if bool(result) == expected else "✗"
        print(f"  {status} {desc}")
        print(f"    文本: {text}")
        print(f"    结果: {result}")

    # 测试5: 三个关键词AND
    print("\n【测试5】三个关键词AND")
    print("规则: airbus+a320+safety")
    test_cases_5 = [
        ("Airbus A320 safety report released", True, "匹配：全部三个关键词"),
        ("Airbus A320 maintenance", False, "不匹配：缺少safety"),
        ("Airbus safety protocols", False, "不匹配：缺少a320"),
        ("A320 safety check", False, "不匹配：缺少airbus"),
    ]
    for text, expected, desc in test_cases_5:
        result = expr_match("airbus+a320+safety", text)
        status = "✓" if bool(result) == expected else "✗"
        print(f"  {status} {desc}")
        print(f"    文本: {text}")
        print(f"    结果: {result}")

    # 测试6: 简单括号 (A|B)+C
    print("\n【测试6】简单括号组合")
    print("规则: (airbus|boeing)+safety")
    test_cases_6 = [
        ("Airbus safety report", True, "匹配：airbus+safety"),
        ("Boeing safety update", True, "匹配：boeing+safety"),
        ("Airbus news", False, "不匹配：缺少safety"),
        ("Safety regulations", False, "不匹配：缺少airbus或boeing"),
    ]
    for text, expected, desc in test_cases_6:
        result = expr_match("(airbus|boeing)+safety", text)
        status = "✓" if bool(result) == expected else "✗"
        print(f"  {status} {desc}")
        print(f"    文本: {text}")
        print(f"    结果: {result}")

    # 测试7: 简单括号 A+(B|C)
    print("\n【测试7】简单括号组合（反向）")
    print("规则: airbus+(a320|a350)")
    test_cases_7 = [
        ("Airbus A320 details", True, "匹配：airbus+a320"),
        ("Airbus A350 update", True, "匹配：airbus+a350"),
        ("Airbus A380 news", False, "不匹配：缺少a320或a350"),
        ("Boeing A320", False, "不匹配：缺少airbus"),
    ]
    for text, expected, desc in test_cases_7:
        result = expr_match("airbus+(a320|a350)", text)
        status = "✓" if bool(result) == expected else "✗"
        print(f"  {status} {desc}")
        print(f"    文本: {text}")
        print(f"    结果: {result}")

    # 测试8: 两组OR的AND - (A|B)+(C|D)
    print("\n【测试8】两组OR的AND组合")
    print("规则: (airbus|boeing)+(a320|737)")
    test_cases_8 = [
        ("Airbus A320 report", True, "匹配：airbus+a320"),
        ("Boeing 737 update", True, "匹配：boeing+737"),
        ("Airbus 737 hybrid", True, "匹配：airbus+737"),
        ("Boeing A320 test", True, "匹配：boeing+a320"),
        ("Airbus A350 news", False, "不匹配：缺少a320或737"),
        ("Embraer E190", False, "不匹配：两组都不匹配"),
    ]
    for text, expected, desc in test_cases_8:
        result = expr_match("(airbus|boeing)+(a320|737)", text)
        status = "✓" if bool(result) == expected else "✗"
        print(f"  {status} {desc}")
        print(f"    文本: {text}")
        print(f"    结果: {result}")

    # 测试9: 空文本和空规则
    print("\n【测试9】边界情况")
    print("规则: airbus")
    test_cases_9 = [
        ("", False, "空文本"),
        ("   ", False, "纯空格"),
        ("No match here", False, "完全不匹配"),
    ]
    for text, expected, desc in test_cases_9:
        result = expr_match("airbus", text)
        status = "✓" if bool(result) == expected else "✗"
        print(f"  {status} {desc}")
        print(f"    文本: '{text}'")
        print(f"    结果: {result}")

    # 测试10: 特殊字符处理
    print("\n【测试10】特殊字符和数字")
    print("规则: a320|737")
    test_cases_10 = [
        ("A320 aircraft", True, "匹配：a320（大写）"),
        ("Boeing 737-800", True, "匹配：737（带连字符）"),
        ("Flight A320-200", True, "匹配：a320（带连字符）"),
        ("Model 747", False, "不匹配：不同型号"),
    ]
    for text, expected, desc in test_cases_10:
        result = expr_match("a320|737", text)
        status = "✓" if bool(result) == expected else "✗"
        print(f"  {status} {desc}")
        print(f"    文本: {text}")
        print(f"    结果: {result}")

    print("\n" + "=" * 80)
    print("简单测试完成！")
    print("=" * 80)

    # 显示缓存统计
    print("\n【缓存统计】")
    cache_info = get_cache_info()
    print(f"缓存版本: {cache_info['version']}")
    print(f"简单搜索缓存: {cache_info['simple_cache']}")
    print(f"正则搜索缓存: {cache_info['regex_cache']}")
    print(f"表达式解析缓存: {cache_info['expression_cache']}")
    print("\n" * 3)
    print("=" * 80)
    print("复杂规则测试")
    print("=" * 80)

    # 测试1: 三层嵌套 - (A|B)+(C|D)+(E|F)
    print("\n【测试1】三层OR+AND组合")
    print("规则: (airbus|boeing)+(a320|737)+(safety|inspection)")
    test_cases_1 = [
        ("Airbus A320 safety report", True, "匹配：airbus+a320+safety"),
        ("Boeing 737 inspection update", True, "匹配：boeing+737+inspection"),
        ("Airbus A350 safety report", False, "不匹配：缺少a320/737"),
        ("Boeing safety protocols", False, "不匹配：缺少a320/737"),
    ]
    for text, expected, desc in test_cases_1:
        result = expr_match(
            "(airbus|boeing)+(a320|737)+(safety|inspection)", text)
        status = "✓" if bool(result) == expected else "✗"
        print(f"  {status} {desc}")
        print(f"    文本: {text}")
        print(f"    结果: {result}")

    # 测试2: 四层嵌套 - ((A+B)|(C+D))+(E|F)
    print("\n【测试2】嵌套AND在OR内部")
    print("规则: ((airbus+a320)|(boeing+737))+(defect|flaw)")
    test_cases_2 = [
        ("Airbus A320 defect found", True, "匹配：(airbus+a320)+defect"),
        ("Boeing 737 flaw detected", True, "匹配：(boeing+737)+flaw"),
        ("Airbus defect report", False, "不匹配：缺少a320"),
        ("Boeing 737 update", False, "不匹配：缺少defect/flaw"),
    ]
    for text, expected, desc in test_cases_2:
        result = expr_match("((airbus+a320)|(boeing+737))+(defect|flaw)", text)
        status = "✓" if bool(result) == expected else "✗"
        print(f"  {status} {desc}")
        print(f"    文本: {text}")
        print(f"    结果: {result}")

    # 测试3: 五层复杂嵌套 - (A|(B+C))+(D|(E+F))
    print("\n【测试3】混合OR和AND的对称结构")
    print("规则: (crash|(accident+investigation))+(pilot|(crew+training))")
    test_cases_3 = [
        ("Crash involving pilot error", True, "匹配：crash+pilot"),
        ("Accident investigation crew training", True,
         "匹配：(accident+investigation)+(crew+training)"),
        ("Crash report released", False, "不匹配：缺少pilot/crew/training"),
        ("Pilot training program", False, "不匹配：缺少crash/accident/investigation"),
    ]
    for text, expected, desc in test_cases_3:
        result = expr_match(
            "(crash|(accident+investigation))+(pilot|(crew+training))", text)
        status = "✓" if bool(result) == expected else "✗"
        print(f"  {status} {desc}")
        print(f"    文本: {text}")
        print(f"    结果: {result}")

    # 测试4: 六层超级复杂 - ((A+B)|(C+D))+((E+F)|(G+H))
    print("\n【测试4】双重嵌套AND+OR组合")
    print("规则: ((airbus+a320)|(boeing+737))+((engine+failure)|(fuel+leak))")
    test_cases_4 = [
        ("Airbus A320 engine failure reported",
         True, "匹配：(airbus+a320)+(engine+failure)"),
        ("Boeing 737 fuel leak incident", True, "匹配：(boeing+737)+(fuel+leak)"),
        ("Airbus A320 maintenance check", False, "不匹配：缺少engine/failure/fuel/leak"),
        ("Engine failure on aircraft", False, "不匹配：缺少airbus+a320或boeing+737"),
    ]
    for text, expected, desc in test_cases_4:
        result = expr_match(
            "((airbus+a320)|(boeing+737))+((engine+failure)|(fuel+leak))", text)
        status = "✓" if bool(result) == expected else "✗"
        print(f"  {status} {desc}")
        print(f"    文本: {text}")
        print(f"    结果: {result}")

    # 测试5: 多关键词OR链 - A|B|C|D|E
    print("\n【测试5】长OR链（5个关键词）")
    print("规则: crash|accident|incident|emergency|disaster")
    test_cases_5 = [
        ("Major disaster strikes city", True, "匹配：disaster"),
        ("Emergency landing successful", True, "匹配：emergency"),
        ("Routine flight completed", False, "不匹配：无关键词"),
    ]
    for text, expected, desc in test_cases_5:
        result = expr_match("crash|accident|incident|emergency|disaster", text)
        status = "✓" if bool(result) == expected else "✗"
        print(f"  {status} {desc}")
        print(f"    文本: {text}")
        print(f"    结果: {result}")

    # 测试6: 多关键词AND链 - A+B+C+D+E
    print("\n【测试6】长AND链（5个关键词）")
    print("规则: airbus+a320+engine+failure+investigation")
    test_cases_6 = [
        ("Airbus A320 engine failure investigation underway", True, "匹配：全部5个关键词"),
        ("Airbus A320 engine failure reported", False, "不匹配：缺少investigation"),
        ("Engine failure investigation on aircraft", False, "不匹配：缺少airbus+a320"),
    ]
    for text, expected, desc in test_cases_6:
        result = expr_match("airbus+a320+engine+failure+investigation", text)
        status = "✓" if bool(result) == expected else "✗"
        print(f"  {status} {desc}")
        print(f"    文本: {text}")
        print(f"    结果: {result}")

    # 测试7: 极端复杂 - (A|(B+C)|(D+E+F))+(G|(H+I))
    print("\n【测试7】不对称嵌套结构")
    print("规则: (crash|(accident+fatal)|(incident+injury+report))+(pilot|(crew+error))")
    test_cases_7 = [
        ("Fatal accident involving pilot", True, "匹配：(accident+fatal)+pilot"),
        ("Incident injury report crew error", True,
         "匹配：(incident+injury+report)+(crew+error)"),
        ("Crash during flight", False, "不匹配：缺少pilot/crew/error"),
        ("Pilot training session", False, "不匹配：缺少crash/accident/incident等"),
    ]
    for text, expected, desc in test_cases_7:
        result = expr_match(
            "(crash|(accident+fatal)|(incident+injury+report))+(pilot|(crew+error))", text)
        status = "✓" if bool(result) == expected else "✗"
        print(f"  {status} {desc}")
        print(f"    文本: {text}")
        print(f"    结果: {result}")

    # 测试8: 三个并列OR组 - (A|B)+(C|D)+(E|F)+(G|H)
    print("\n【测试8】四组OR的AND组合")
    print("规则: (airbus|boeing)+(a320|737)+(engine|fuel)+(failure|leak)")
    test_cases_8 = [
        ("Airbus A320 engine failure analysis",
         True, "匹配：airbus+a320+engine+failure"),
        ("Boeing 737 fuel leak detected", True, "匹配：boeing+737+fuel+leak"),
        ("Airbus A320 engine maintenance", False, "不匹配：缺少failure/leak"),
        ("Engine failure on aircraft", False, "不匹配：缺少airbus/boeing和a320/737"),
    ]
    for text, expected, desc in test_cases_8:
        result = expr_match(
            "(airbus|boeing)+(a320|737)+(engine|fuel)+(failure|leak)", text)
        status = "✓" if bool(result) == expected else "✗"
        print(f"  {status} {desc}")
        print(f"    文本: {text}")
        print(f"    结果: {result}")

    # 测试9: 深度嵌套 - (((A+B)|C)+D)|(E+F)
    print("\n【测试9】深度嵌套（3层括号）")
    print("规则: (((airbus+a320)|boeing)+safety)|(crash+investigation)")
    test_cases_9 = [
        ("Airbus A320 safety review", True, "匹配：(airbus+a320)+safety"),
        ("Boeing safety protocols", True, "匹配：boeing+safety"),
        ("Crash investigation report", True, "匹配：crash+investigation"),
        ("Airbus maintenance check", False, "不匹配：不符合任何分支"),
    ]
    for text, expected, desc in test_cases_9:
        result = expr_match(
            "(((airbus+a320)|boeing)+safety)|(crash+investigation)", text)
        status = "✓" if bool(result) == expected else "✗"
        print(f"  {status} {desc}")
        print(f"    文本: {text}")
        print(f"    结果: {result}")

    # 测试10: 超长OR+AND混合
    print("\n【测试10】超长混合表达式（10个关键词）")
    print("规则: (airbus|boeing|embraer)+(a320|737|e190)+(engine|fuel|hydraulic)+(failure|leak|malfunction)")
    test_cases_10 = [
        ("Embraer E190 hydraulic malfunction", True,
         "匹配：embraer+e190+hydraulic+malfunction"),
        ("Airbus A320 fuel leak emergency", True, "匹配：airbus+a320+fuel+leak"),
        ("Boeing 737 engine maintenance", False, "不匹配：缺少failure/leak/malfunction"),
    ]
    for text, expected, desc in test_cases_10:
        result = expr_match(
            "(airbus|boeing|embraer)+(a320|737|e190)+(engine|fuel|hydraulic)+(failure|leak|malfunction)", text)
        status = "✓" if bool(result) == expected else "✗"
        print(f"  {status} {desc}")
        print(f"    文本: {text}")
        print(f"    结果: {result}")

    print("\n" + "=" * 80)
    print("测试完成！")
    print("=" * 80)

    # 显示缓存统计
    print("\n【缓存统计】")
    cache_info = get_cache_info()
    print(f"缓存版本: {cache_info['version']}")
    print(f"简单搜索缓存: {cache_info['simple_cache']}")
    print(f"正则搜索缓存: {cache_info['regex_cache']}")
    print(f"表达式解析缓存: {cache_info['expression_cache']}")
