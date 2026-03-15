# Product Requirements

## Overview

Barbooks AI is a backend application that uses an AI agent to validate answers to trivia questions embedded in physical books. Each book page has a QR code that links to a question-specific page, where users can interact with an AI agent to check their answers.

## Requirements

- Book pages have a QR code linking to a domain we control
- QR code communicates book ID, version, and page number to the backend
- Backend runs an AI agent that validates answers to questions in the book
- AI agent can provide hints
- AI agent provides short responses
- When a correct individual answer is provided, the agent validates and states the position (e.g., "Correct! That's the Nth team on the list.")
- Results are not saved beyond the current session
- Backend uses spreadsheets as a database for book content and answer links

## Example

**Book Question:** "List the top 20 all-time NFL touchdown leaders."

**Answer site:** `https://www.espn.com/nfl/history/leaders/_/stat/touchdown`

**QR Code:** `https://barbooks.ai/book/nfl/leaders/touchdown`

| User | Agent |
|------|-------|
| "Is Tom Brady on this list?" | "No, Tom Brady is not on this list." |
| "Randy Moss?" | "Yes, Randy Moss is 4th on the list with 157 TD's" |
