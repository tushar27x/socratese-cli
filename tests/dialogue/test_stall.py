# tests/dialogue/test_stall.py
from socratese.dialogue.stall import content_words, is_stalled, orbiting_terms

TOPIC = "how does the attention mechanism work?"

# Five rewordings of one unanswered question, taken from a real 11-turn
# transcript. No two are near-duplicates, which is why pairwise similarity
# misses this and a sliding window does not.
ORBITING = [
    "Your notes say a high score means the model will use more of the value vector — what does it mean to use more of a vector?",
    "If the score is high and you use more of V, what happens to V when you scale it by a low score instead?",
    "If the dot product gives you a score, what operation would let you use more of the value vector with V?",
    "If you have a high score and a value vector V, what single operation uses more of V?",
    "If you have a score and want it to control how much of vector V is used, what operation connects a number to a vector?",
]

# A healthy run: each question moves to a different part of the mechanism.
PROGRESSING = [
    "When the model computes Q · K for a token, what is it measuring between those two vectors?",
    "What does it mean for a value to matter more — what does the model do with that information?",
    "You said the token is more relevant, but the model computes Q · K, not Q · V. What role does V play?",
    "What happens after you normalize them — how do the value vectors combine into a single output?",
]


def test_a_progressing_conversation_is_not_stalled():
    assert not is_stalled(PROGRESSING, TOPIC)


def test_rewordings_of_one_question_are_detected():
    assert is_stalled(ORBITING, TOPIC)


def test_the_shared_terms_are_reported():
    """The warning names them, so they have to be the actual subject."""
    assert orbiting_terms(ORBITING, TOPIC) == {"score"}


def test_a_short_conversation_is_never_stalled():
    """Fewer questions than the window cannot establish a pattern."""
    assert not is_stalled(ORBITING[:3], TOPIC)
    assert not is_stalled([], TOPIC)


def test_only_the_most_recent_questions_count():
    """A conversation that circled and then recovered is not stalled — the
    window slides, so old repetition ages out."""
    recovered = ORBITING + PROGRESSING

    assert not is_stalled(recovered, TOPIC)


def test_topic_words_do_not_count_as_circling():
    """Every question in a session about React mentions React. That is the
    subject, not evidence of going in circles."""
    about_react = [
        "What does React compare to find changes?",
        "Which two things does React hold?",
        "When React updates, what happens first?",
        "Why would React avoid reading the browser directly?",
    ]

    assert not is_stalled(about_react, "how does react.js use the virtual DOM?")
    assert is_stalled(about_react, "")  # without the topic, "react" looks like circling


def test_stopwords_are_not_subject_matter():
    assert content_words("What do you say about that?") == set()
    assert content_words("what does softmax do") == {"softmax"}


def test_the_window_is_configurable():
    assert is_stalled(ORBITING[:3], TOPIC, window=3)
    assert not is_stalled(ORBITING[:3], TOPIC, window=4)
