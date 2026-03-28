window.addEventListener('message', function(e) {
    if (e.data && e.data.type === 'jump_to_line') {
        const targetHost = document.querySelector('.main-code-editor');
        if (!targetHost || !targetHost.shadowRoot) return;
        
        // Panel appends the Ace Editor div to its Shadow DOM component
        const aceElement = targetHost.shadowRoot.querySelector('.ace_editor');
        if (aceElement && window.ace) {
            // Retrieve Ace instance
            const editorInstance = window.ace.edit(aceElement);
            // gotoLine args: line, column, animate
            editorInstance.gotoLine(e.data.line, 0, true);
            editorInstance.focus();
            
            // Highlight the line briefly
            var Range = window.ace.require("ace/range").Range;
            var mrk = editorInstance.session.addMarker(
                new Range(e.data.line - 1, 0, e.data.line - 1, 1),
                "ace_active-line", 
                "fullLine"
            );
            setTimeout(() => {
                editorInstance.session.removeMarker(mrk);
            }, 1000);
        }
    }
});
