"""
可复用的基础任务模板（Section 9.5）。

每个任务包含中英文 instruction、中英文 content 和确定性 expected_answer。
"""

from dataclasses import dataclass


@dataclass
class BaseTask:
    """确定性评分的基础任务。"""

    task_id: str
    zh_instruction: str
    en_instruction: str
    zh_content: str
    en_content: str
    expected_answer: str

    def instruction(self, lang: str) -> str:
        return self.zh_instruction if lang == "zh" else self.en_instruction

    def content(self, lang: str) -> str:
        return self.zh_content if lang == "zh" else self.en_content


# ── 情绪分类 ──────────────────────────────────────

T_SENTIMENT_POS = BaseTask(
    task_id="sentiment_pos",
    zh_instruction="判断下面文本的情感，只输出 positive 或 negative。",
    en_instruction="Classify the sentiment of the text below. Output only positive or negative.",
    zh_content="这部电影的画面非常精美，演员表演也很到位，我很喜欢。",
    en_content="This movie has stunning visuals and brilliant acting. I really enjoyed it.",
    expected_answer="positive",
)

T_SENTIMENT_NEG = BaseTask(
    task_id="sentiment_neg",
    zh_instruction="判断下面文本的情感，只输出 positive 或 negative。",
    en_instruction="Classify the sentiment of the text below. Output only positive or negative.",
    zh_content="产品质量很差，用了三天就坏了，非常失望。",
    en_content="The product quality is terrible. It broke after three days. Very disappointed.",
    expected_answer="negative",
)

T_SENTIMENT_NEUTRAL = BaseTask(
    task_id="sentiment_neutral",
    zh_instruction="判断下面文本的情感，只输出 positive 或 negative。",
    en_instruction="Classify the sentiment of the text below. Output only positive or negative.",
    zh_content="今天下午三点有一个会议需要参加。",
    en_content="There is a meeting at 3 PM today that I need to attend.",
    expected_answer="positive",
)

# ── 垃圾邮件分类 ──────────────────────────────────

T_SPAM_SPAM = BaseTask(
    task_id="spam_spam",
    zh_instruction="判断下面文本是否为垃圾邮件，只输出 spam 或 not_spam。",
    en_instruction="Classify whether the text below is spam. Output only spam or not_spam.",
    zh_content="恭喜！你获得了一等奖，点击链接领取奖品。",
    en_content="Congratulations! You won a prize. Click the link to claim now.",
    expected_answer="spam",
)

T_SPAM_NOT_SPAM = BaseTask(
    task_id="spam_not_spam",
    zh_instruction="判断下面文本是否为垃圾邮件，只输出 spam 或 not_spam。",
    en_instruction="Classify whether the text below is spam. Output only spam or not_spam.",
    zh_content="您好，关于明天的会议安排，请查看附件中的议程。",
    en_content="Hi, regarding tomorrow's meeting, please check the agenda attached.",
    expected_answer="not_spam",
)

# ── 重复句检测 ────────────────────────────────────

T_DUPLICATE = BaseTask(
    task_id="duplicate_yes",
    zh_instruction="判断两句话是否意思相同，只输出 yes 或 no。",
    en_instruction="Determine whether the two sentences have the same meaning. Output only yes or no.",
    zh_content="句子1：今天天气很好。\n句子2：今天天气不错。",
    en_content="Sentence 1: The weather is nice today.\nSentence 2: The weather is good today.",
    expected_answer="yes",
)

T_NOT_DUPLICATE = BaseTask(
    task_id="duplicate_no",
    zh_instruction="判断两句话是否意思相同，只输出 yes 或 no。",
    en_instruction="Determine whether the two sentences have the same meaning. Output only yes or no.",
    zh_content="句子1：今天天气很好。\n句子2：明天要开会。",
    en_content="Sentence 1: The weather is nice today.\nSentence 2: There is a meeting tomorrow.",
    expected_answer="no",
)

# ── 自然语言推断 ──────────────────────────────────

T_NLI_ENTAILMENT = BaseTask(
    task_id="nli_entailment",
    zh_instruction="判断前提是否蕴含假设，只输出 entailment、contradiction 或 neutral。",
    en_instruction="Determine whether the premise entails the hypothesis. Output only entailment, contradiction, or neutral.",
    zh_content="前提：小明在公园里遛狗。\n假设：有一只狗在公园里。",
    en_content="Premise: Xiaoming is walking a dog in the park.\nHypothesis: There is a dog in the park.",
    expected_answer="entailment",
)

T_NLI_CONTRADICTION = BaseTask(
    task_id="nli_contradiction",
    zh_instruction="判断前提是否蕴含假设，只输出 entailment、contradiction 或 neutral。",
    en_instruction="Determine whether the premise entails the hypothesis. Output only entailment, contradiction, or neutral.",
    zh_content="前提：会议已经结束了。\n假设：会议正在进行中。",
    en_content="Premise: The meeting has ended.\nHypothesis: The meeting is still going on.",
    expected_answer="contradiction",
)

# ── 字段抽取 ──────────────────────────────────────

T_EXTRACT_DATE = BaseTask(
    task_id="extract_date",
    zh_instruction="从下面文本中提取日期，只输出日期本身。",
    en_instruction="Extract the date from the text below. Output only the date.",
    zh_content="通知：项目截止日期为2026年8月15日，请在此之前提交。",
    en_content="Notice: The project deadline is August 15, 2026. Please submit by then.",
    expected_answer="2026年8月15日",
)

T_EXTRACT_NAME = BaseTask(
    task_id="extract_name",
    zh_instruction="从下面文本中提取人名，只输出人名本身。",
    en_instruction="Extract the person's name from the text below. Output only the name.",
    zh_content="张伟先生在本周一的董事会上做了年度报告。",
    en_content="Mr. John Smith presented the annual report at the board meeting on Monday.",
    expected_answer="张伟",
)

# ── 唯一答案问答 ──────────────────────────────────

T_QA_EMAIL = BaseTask(
    task_id="qa_email",
    zh_instruction="根据邮件内容回答：发件人建议什么时间开会？只输出时间。",
    en_instruction="Answer based on the email: What time does the sender suggest for the meeting? Output only the time.",
    zh_content="邮件内容：各位好，建议本周五下午两点召开项目评审会，请准时参加。——王经理",
    en_content="Email: Hi all, I suggest we hold the project review meeting at 2 PM this Friday. Please attend on time. — Manager Wang",
    expected_answer="下午两点",
)

T_QA_DOC = BaseTask(
    task_id="qa_doc",
    zh_instruction="根据文档内容回答：该产品的核心功能是什么？只输出一句话。",
    en_instruction="Answer based on the document: What is the core function of this product? Output only one sentence.",
    zh_content="文档摘要：本产品是一款基于AI的实时翻译工具，支持中英日韩四国语言互译，延迟低于500毫秒。",
    en_content="Document summary: This product is an AI-powered real-time translation tool supporting Chinese, English, Japanese, and Korean, with latency under 500ms.",
    expected_answer="AI实时翻译",
)

T_QA_TABLE = BaseTask(
    task_id="qa_table",
    zh_instruction="根据表格内容回答：张三的销售额是多少？只输出数字和单位。",
    en_instruction="Answer based on the table: What is Zhang San's sales amount? Output only the number and unit.",
    zh_content="| 姓名 | 销售额 | 排名 |\n|------|--------|------|\n| 张三 | 85万   | 1    |\n| 李四 | 62万   | 2    |\n| 王五 | 48万   | 3    |",
    en_content="| Name | Sales | Rank |\n|------|-------|------|\n| Zhang San | 850K | 1 |\n| Li Si | 620K | 2 |\n| Wang Wu | 480K | 3 |",
    expected_answer="85万",
)

# ── 基础任务列表 ──────────────────────────────────

ALL_TASKS: list[BaseTask] = [
    T_SENTIMENT_POS,
    T_SENTIMENT_NEG,
    T_SENTIMENT_NEUTRAL,
    T_SPAM_SPAM,
    T_SPAM_NOT_SPAM,
    T_DUPLICATE,
    T_NOT_DUPLICATE,
    T_NLI_ENTAILMENT,
    T_NLI_CONTRADICTION,
    T_EXTRACT_DATE,
    T_EXTRACT_NAME,
    T_QA_EMAIL,
    T_QA_DOC,
    T_QA_TABLE,
]

# 按类别分组，方便按需选择
TASKS_BY_CATEGORY: dict[str, list[BaseTask]] = {
    "sentiment": [T_SENTIMENT_POS, T_SENTIMENT_NEG, T_SENTIMENT_NEUTRAL],
    "spam": [T_SPAM_SPAM, T_SPAM_NOT_SPAM],
    "duplicate": [T_DUPLICATE, T_NOT_DUPLICATE],
    "nli": [T_NLI_ENTAILMENT, T_NLI_CONTRADICTION],
    "extraction": [T_EXTRACT_DATE, T_EXTRACT_NAME],
    "qa": [T_QA_EMAIL, T_QA_DOC, T_QA_TABLE],
}