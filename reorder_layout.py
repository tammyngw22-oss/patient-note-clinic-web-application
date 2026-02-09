
import os

FILE_PATH = 'frontend/index.html'

def reorder_layout():
    with open(FILE_PATH, 'r') as f:
        lines = f.readlines()

    # Find start of Input Area
    input_start_idx = -1
    for i, line in enumerate(lines):
        if '{/* Input Area */}' in line:
            input_start_idx = i
            break
            
    if input_start_idx == -1:
        print("Could not find Input Area start")
        return

    # Find start of Timeline List (which marks end of Input Area)
    timeline_start_idx = -1
    for i, line in enumerate(lines):
        if '{/* Timeline List */}' in line:
            timeline_start_idx = i
            break
            
    if timeline_start_idx == -1:
        print("Could not find Timeline List start")
        return

    # Find end of Timeline List
    # It starts at timeline_start_idx
    # The next line should be the div opening.
    # We need to find the matching closing div.
    # Since we know the indentation, we can look for the closing div with same indentation?
    # Or just look for the closing div of the container?
    # Actually, looking at the code:
    # The Timeline List div is closed, and then immediately follows `</div>` for the container, and `</div>` for the Main Content Area.
    
    # Let's count braces or divs? No, that's brittle.
    # Let's look at indentation.
    # Input Area indentation: 28 spaces (based on previous analysis)
    # Timeline List indentation: 28 spaces
    
    # The Input Area block is from input_start_idx to timeline_start_idx (exclusive).
    input_block = lines[input_start_idx:timeline_start_idx]
    
    # The Timeline List block starts at timeline_start_idx.
    # We need to find where it ends.
    # It ends before the closing of the parent div.
    # The parent div is `<div className="flex-1 flex flex-col bg-white min-w-0">`
    # Its closing div is indented with 24 spaces.
    
    timeline_end_idx = -1
    for i in range(timeline_start_idx, len(lines)):
        line = lines[i]
        # Check for closing div of the parent container (indentation 24 spaces)
        # The timeline list itself is indented with 28 spaces.
        # So its closing div should be 28 spaces.
        # But we need to be careful.
        
        # Let's look at the file content again.
        # Line 1149: `                            </div>` (28 spaces) - closes Timeline List
        # Line 1150: `                        </div>` (24 spaces) - closes Parent
        
        if line.strip() == '</div>' and len(line) - len(line.lstrip()) == 24:
            timeline_end_idx = i
            break
            
    if timeline_end_idx == -1:
        print("Could not find Timeline List end")
        return

    timeline_block = lines[timeline_start_idx:timeline_end_idx]

    # Modify Input Block border
    # <div className="p-4 border-b bg-gray-50"> -> <div className="p-4 border-t bg-gray-50">
    new_input_block = []
    for line in input_block:
        if 'border-b' in line and 'bg-gray-50' in line:
            new_input_block.append(line.replace('border-b', 'border-t'))
        else:
            new_input_block.append(line)
            
    # Construct new content
    # Before Input Area
    new_lines = lines[:input_start_idx]
    # Add Timeline Block
    new_lines.extend(timeline_block)
    # Add Input Block
    new_lines.extend(new_input_block)
    # After Timeline List (which was the end of the container content)
    new_lines.extend(lines[timeline_end_idx:])
    
    with open(FILE_PATH, 'w') as f:
        f.writelines(new_lines)
        
    print("Successfully reordered layout")

if __name__ == '__main__':
    reorder_layout()
