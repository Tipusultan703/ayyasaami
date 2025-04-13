document.addEventListener('DOMContentLoaded', function () {
    // Tab Switching
    const tabButtons = document.querySelectorAll('.tab-button');
    const tabContents = document.querySelectorAll('.tab-content');

    tabButtons.forEach(button => {
        button.addEventListener('click', () => {
            tabButtons.forEach(btn => btn.classList.remove('active'));
            tabContents.forEach(content => content.classList.remove('active'));
            button.classList.add('active');
            const tabId = button.getAttribute('data-tab');
            document.getElementById(tabId).classList.add('active');
        });
    });

    // Button Event Listeners
    const analyzeBtn = document.getElementById('analyze-btn');
    const analyzeTextBtn = document.getElementById('analyze-text-btn');
    const compareBtn = document.getElementById('compare-btn');

    if (analyzeBtn) analyzeBtn.addEventListener('click', analyzeUrl);
    if (analyzeTextBtn) analyzeTextBtn.addEventListener('click', analyzeText);
    if (compareBtn) compareBtn.addEventListener('click', compareArticles);
});

async function analyzeUrl() {
    const urlInput = document.getElementById('url-input').value.trim();
    if (!urlInput) return alert('Please enter a URL');

    showLoading('analyze');
    hideResults('analyze');

    try {
        const res = await fetch('/api/analyze-url', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: urlInput })
        });

        if (!res.ok) throw new Error(`API error: ${res.status}`);
            
        const data = await res.json();
        
        if (data.error) throw new Error(data.error);
        
        displayResults(data);
        showResults('analyze');
    } catch (err) {
        console.error("Analysis error:", err);
        alert(`Error analyzing URL: ${err.message}`);
    } finally {
        hideLoading('analyze');
    }
}

async function analyzeText() {
    const textInput = document.getElementById('text-input').value.trim();
    if (!textInput || textInput.length < 50) {
        return alert('Please enter at least 50 characters for analysis');
    }

    showLoading('analyze');
    hideResults('analyze');

    try {
        const res = await fetch('/api/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: textInput })
        });

        if (!res.ok) throw new Error(`API error: ${res.status}`);
        
        const data = await res.json();
        
        if (data.error) throw new Error(data.error);

        const displayData = {
            ...data,
            title: "Custom Text Analysis",
            date: new Date().toISOString().split('T')[0],
            source: "User-provided text",
            credibility: "N/A"
        };

        displayResults(displayData);
        showResults('analyze');
    } catch (err) {
        console.error("Analysis error:", err);
        alert(`Error analyzing text: ${err.message}`);
    } finally {
        hideLoading('analyze');
    }
}

async function compareArticles() {
    const urlInput = document.getElementById('compare-url-input').value.trim();
    if (!urlInput) return alert('Please enter a URL to compare');

    showLoading('compare');
    hideResults('compare');

    try {
        const res = await fetch('/api/compare-news', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: urlInput })
        });

        if (!res.ok) {
            const errorData = await res.json();
            throw new Error(errorData.error || `API error: ${res.status}`);
        }
        
        const data = await res.json();
        
        if (data.error) throw new Error(data.error);

        displayComparisonResults(data);
    } catch (err) {
        console.error("Comparison error:", err);
        showManualComparisonOption(err.message);
    } finally {
        hideLoading('compare');
    }
}

function showLoading(context = 'analyze') {
    const element = document.getElementById(`${context}-loading`);
    if (element) element.classList.remove('hidden');
}

function hideLoading(context = 'analyze') {
    const element = document.getElementById(`${context}-loading`);
    if (element) element.classList.add('hidden');
}

function hideResults(context = 'analyze') {
    const element = document.getElementById(`${context}-results`);
    if (element) element.classList.add('hidden');
}

function showResults(context = 'analyze') {
    const element = document.getElementById(`${context}-results`);
    if (element) element.classList.remove('hidden');
}

function getBiasClass(score) {
    if (score === null || score === undefined) return '';
    if (score < 40) return 'bias-low';
    if (score < 70) return 'bias-medium';
    return 'bias-high';
}

function displayResults(data) {
    if (!data) {
        alert('No analysis results received');
        return;
    }

    document.getElementById('source').textContent = data.source || 'Unknown';
    document.getElementById('credibility').textContent = data.credibility || 'Unknown';
    document.getElementById('credibility').className = `value cred-${(data.credibility || '').toLowerCase()}`;
    
    const biasScore = data.bias_score !== undefined ? data.bias_score : null;
    document.getElementById('bias-score').textContent = biasScore !== null ? `${biasScore}/100` : 'N/A';
    
    const meterFill = document.getElementById('meter-fill');
    meterFill.className = 'meter-fill';
    if (biasScore !== null) {
        meterFill.style.width = `${biasScore}%`;
        meterFill.classList.add(
            biasScore < 40 ? 'meter-low' :
            biasScore < 70 ? 'meter-medium' :
            'meter-high'
        );
    }

    document.getElementById('article-date').textContent = data.date || 'Unknown date';
    document.getElementById('rewritten-text').textContent = data.rewritten || 'Could not generate neutral version';
    
    const redlinedText = document.getElementById('redlined-text');
    if (data.redlined_text?.biased_words?.length > 0) {
        let html = '<p><strong>Biased words detected:</strong></p><ul>';
        data.redlined_text.biased_words.forEach((word, i) => {
            const alt = data.redlined_text.neutral_alternatives[i] || 'No alternative suggested';
            html += `<li><span class="biased-word">${word}</span> → <span class="neutral-word">${alt}</span></li>`;
        });
        html += '</ul>';
        redlinedText.innerHTML = html;
    } else {
        redlinedText.textContent = 'No biased words detected or analysis failed.';
    }

    document.getElementById('original-text').textContent = data.original_text || 'No original text available.';
}

function displayComparisonResults(data) {
    if (!data) {
        console.error("No data received for comparison");
        showManualComparisonOption("");
        return;
    }

    const mainTopicEl = document.getElementById('main-topic');
    const compareDateEl = document.getElementById('comparison-date');
    if (mainTopicEl) mainTopicEl.textContent = data.main_topic || 'Unknown topic';
    if (compareDateEl) compareDateEl.textContent = data.comparison_date || 'Unknown date';

    // Display original article
    const original = data.original_article || {};
    const originalContainer = document.getElementById('original-article-details');
    if (originalContainer) {
        originalContainer.innerHTML = `
            <div class="article-header">
                <h3>${original.source || 'Unknown Source'}</h3>
                <div class="article-meta">
                    <span class="timestamp">${original.timestamp || 'Unknown date'}</span>
                    <span class="bias-score ${getBiasClass(original.bias_score)}">
                        ${original.bias_score !== undefined ? original.bias_score + '/100' : 'N/A'}
                    </span>
                    <span class="credibility cred-${(original.credibility || '').toLowerCase()}">
                        ${original.credibility || 'Unknown'} Credibility
                    </span>
                </div>
            </div>
            <div class="article-original">
                <h4>Original Text</h4>
                <div class="text-content">${original.original_text || 'No original text available.'}</div>
            </div>
            <div class="article-rewritten">
                <h4>Neutral Rewrite</h4>
                <div class="text-content">${original.rewritten || 'No rewritten version available.'}</div>
            </div>
            <div class="article-bias">
                <h4>Bias Analysis</h4>
                <div class="bias-meter">
                    <div class="meter-fill ${getBiasClass(original.bias_score)}" 
                        style="width: ${original.bias_score || 0}%"></div>
                </div>
                ${original.redlined_text?.biased_words?.length > 0 ? 
                    `<div class="biased-words">
                        <h5>Biased Language Detected:</h5>
                        <ul>
                            ${original.redlined_text.biased_words.map((word, i) => `
                                <li><span class="biased-word">${word}</span> → 
                                    <span class="neutral-word">
                                        ${original.redlined_text.neutral_alternatives[i] || 'No alternative'}
                                    </span>
                                </li>
                            `).join('')}
                        </ul>
                    </div>` : 
                    '<p>No significant biased language detected</p>'
                }
            </div>
        `;
    }

    // Display comparison articles
    const container = document.getElementById('comparison-articles');
    if (container) {
        container.innerHTML = '';

        if (data.comparison_articles?.length) {
            data.comparison_articles.forEach(article => {
                const div = document.createElement('div');
                div.className = 'article-card';
                div.innerHTML = `
                    <div class="article-header">
                        <span class="source">${article.source || 'Unknown'}</span>
                        <span class="timestamp">${article.timestamp || 'Unknown time'}</span>
                        <div class="article-scores">
                            <span class="bias-score ${getBiasClass(article.bias_score)}">
                                ${article.bias_score !== undefined ? article.bias_score + '/100' : 'N/A'}
                            </span>
                            ${article.similarity_score ? 
                                `<span class="similarity-score">
                                    ${article.similarity_score}% Match
                                </span>` : ''
                            }
                        </div>
                    </div>
                    <div class="article-original">
                        <h4>Original Text</h4>
                        <div class="text-content">${article.original_text || 'No original text available.'}</div>
                    </div>
                    <div class="article-rewritten">
                        <h4>Neutral Rewrite</h4>
                        <div class="text-content">${article.rewritten || 'No rewritten version available.'}</div>
                    </div>
                    <a href="${article.original_url}" target="_blank" class="view-original">View Original Article</a>
                `;
                container.appendChild(div);
            });
        } else {
            showManualComparisonOption(data.main_topic || "");
        }
    }

    const resultsContainer = document.getElementById('compare-results');
    if (resultsContainer) resultsContainer.classList.remove('hidden');
}

function showManualComparisonOption(searchQuery = "") {
    const container = document.getElementById('comparison-articles');
    if (!container) return;
    
    container.innerHTML = `
        <div class="no-auto-results">
            <div class="warning-message">
                <i class="fas fa-exclamation-triangle"></i>
                <h4>Couldn't find automatic comparisons</h4>
            </div>
            
            <div class="manual-option">
                <p>To compare with other sources:</p>
                <ol>
                    <li>Find similar articles on these sites:</li>
                    <div class="search-buttons">
                        <a href="https://news.google.com/search?q=${encodeURIComponent(searchQuery)}" 
                           target="_blank" class="search-btn">
                           <i class="fab fa-google"></i> Google News
                        </a>
                        <a href="https://www.bing.com/news/search?q=${encodeURIComponent(searchQuery)}" 
                           target="_blank" class="search-btn">
                           <i class="fab fa-microsoft"></i> Bing News
                        </a>
                    </div>
                    
                    <li>Copy text from another article</li>
                    <li>Paste it in the <strong>Analyze Text</strong> tab above</li>
                </ol>
            </div>
        </div>
    `;
    
    const resultsContainer = document.getElementById('compare-results');
    if (resultsContainer) resultsContainer.classList.remove('hidden');
}