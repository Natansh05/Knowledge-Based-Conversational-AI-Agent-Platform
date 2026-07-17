from rake_nltk import Rake

def extract_document_topics(text: str, top_n: int = 5) -> list:
    """
    Extracts the top N keywords/topics from a document using RAKE.

    Args:
        text (str): Full text of the document
        top_n (int): Number of top topics to return

    Returns:
        List[str]: List of top keywords/phrases
    """
    # 1. Initialize RAKE
    rake = Rake()  # Uses NLTK stopwords by default

    # 2. Extract keywords
    rake.extract_keywords_from_text(text)

    # 3. Get ranked phrases
    ranked_phrases_with_scores = rake.get_ranked_phrases_with_scores()

    # 4. Sort and take top N
    top_phrases = [phrase for score, phrase in sorted(ranked_phrases_with_scores, reverse=True)][:top_n]

    return top_phrases