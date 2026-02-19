def cap_text_length(text: str, max_length: int = 100) -> str:
	"""
	Cap the length of the text to the specified max_length, adding an ellipsis if truncated.
	"""
	if len(text) <= max_length:
		return text
	return text[:max_length] + '...'
