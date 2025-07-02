from flask import Flask, render_template, request, redirect, url_for, send_from_directory, flash
import os
import hashlib
import json
import time
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['BLOCKCHAIN_FILE'] = 'blockchain.json'

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

class Block:
    def __init__(self, index, timestamp, file_data, previous_hash):
        self.index = index
        self.timestamp = timestamp
        self.file_data = file_data
        self.previous_hash = previous_hash
        self.hash = self.calculate_hash()
    
    def calculate_hash(self):
        block_string = json.dumps({
            "index": self.index,
            "timestamp": self.timestamp,
            "file_data": self.file_data,
            "previous_hash": self.previous_hash
        }, sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()
    
    @classmethod
    def from_dict(cls, block_dict):
        """Create a Block instance from a dictionary"""
        block = cls(
            block_dict["index"],
            block_dict["timestamp"],
            block_dict["file_data"],
            block_dict["previous_hash"]
        )
        # Ensure the hash matches what's stored
        block.hash = block_dict["hash"]
        return block

class Blockchain:
    def __init__(self):
        self.chain = []
        self.create_genesis_block()
        self.validation_errors = []
    
    def create_genesis_block(self):
        genesis_block = Block(0, time.time(), {"filename": "genesis", "file_hash": "0"}, "0")
        self.chain.append(genesis_block.__dict__)
    
    def get_latest_block(self):
        return self.chain[-1]
    
    def add_block(self, file_data):
        previous_block = self.get_latest_block()
        new_block = Block(
            len(self.chain),
            time.time(),
            file_data,
            previous_block["hash"]
        )
        self.chain.append(new_block.__dict__)
        return new_block
    
    def is_chain_valid(self):
        self.validation_errors = []
        
        if len(self.chain) == 0:
            self.validation_errors.append("Blockchain is empty")
            return False
            
        # Check genesis block
        if self.chain[0]["index"] != 0 or self.chain[0]["previous_hash"] != "0":
            self.validation_errors.append("Invalid genesis block")
            return False
        
        for i in range(1, len(self.chain)):
            current_block = self.chain[i]
            previous_block = self.chain[i-1]
            
            # Recreate the block to calculate its hash
            recreated_block = Block(
                current_block["index"],
                current_block["timestamp"],
                current_block["file_data"],
                current_block["previous_hash"]
            )
            
            # Check if hash is correct
            if current_block["hash"] != recreated_block.calculate_hash():
                self.validation_errors.append(f"Invalid hash for block {i}")
                return False
            
            # Check if previous hash matches
            if current_block["previous_hash"] != previous_block["hash"]:
                self.validation_errors.append(f"Invalid previous hash reference in block {i}")
                return False
            
            # Check if index is sequential
            if current_block["index"] != i:
                self.validation_errors.append(f"Non-sequential block index at position {i}")
                return False
        
        return True
    
    def repair_chain(self):
        """Attempt to repair the blockchain by recalculating hashes and fixing links"""
        if len(self.chain) <= 1:
            # Just reset if only genesis block or empty
            self.chain = []
            self.create_genesis_block()
            return True
            
        valid_chain = [self.chain[0]]  # Keep genesis block
        
        # Rebuild the chain with correct hashes and links
        for i in range(1, len(self.chain)):
            current_block = self.chain[i]
            previous_block = valid_chain[-1]
            
            # Create a new block with correct previous hash
            new_block = Block(
                i,  # Ensure sequential index
                current_block["timestamp"],
                current_block["file_data"],
                previous_block["hash"]  # Link to previous block correctly
            )
            
            valid_chain.append(new_block.__dict__)
        
        self.chain = valid_chain
        return True
    
    def save_to_file(self, filename):
        with open(filename, 'w') as f:
            json.dump(self.chain, f, indent=4)
    
    def load_from_file(self, filename):
        try:
            if os.path.exists(filename):
                with open(filename, 'r') as f:
                    self.chain = json.load(f)
                
                # Validate the loaded chain
                if not self.is_chain_valid():
                    print(f"Warning: Loaded blockchain is invalid: {self.validation_errors}")
            else:
                self.create_genesis_block()
                self.save_to_file(filename)
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            print(f"Error loading blockchain: {str(e)}")
            self.chain = []
            self.create_genesis_block()
            self.save_to_file(filename)

# Initialize blockchain
blockchain = Blockchain()
blockchain.load_from_file(app.config['BLOCKCHAIN_FILE'])

def calculate_file_hash(file_path):
    """Calculate SHA-256 hash of a file"""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

@app.route('/')
def index():
    # Get list of files from blockchain
    files = []
    for block in blockchain.chain[1:]:  # Skip genesis block
        files.append({
            'filename': block['file_data']['filename'],
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(block['timestamp'])),
            'hash': block['file_data']['file_hash'],
            'block_index': block['index']
        })
    
    is_valid = blockchain.is_chain_valid()
    validation_errors = blockchain.validation_errors if not is_valid else []
    
    return render_template('index.html', 
                          files=files, 
                          chain_valid=is_valid,
                          validation_errors=validation_errors)

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        flash('No file part')
        return redirect(request.url)
    
    file = request.files['file']
    if file.filename == '':
        flash('No selected file')
        return redirect(request.url)
    
    if file:
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        # Calculate file hash
        file_hash = calculate_file_hash(file_path)
        
        # Add to blockchain
        file_data = {
            "filename": filename,
            "file_hash": file_hash
        }
        blockchain.add_block(file_data)
        
        # Verify blockchain integrity after adding block
        if blockchain.is_chain_valid():
            blockchain.save_to_file(app.config['BLOCKCHAIN_FILE'])
            flash(f'File {filename} uploaded and added to blockchain')
        else:
            flash(f'Error: Failed to add file to blockchain. Validation errors: {", ".join(blockchain.validation_errors)}')
        
        return redirect(url_for('index'))

@app.route('/download/<filename>')
def download_file(filename):
    # Verify file integrity before download
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if os.path.exists(file_path):
        current_hash = calculate_file_hash(file_path)
        
        # Find file in blockchain
        file_block = None
        for block in blockchain.chain:
            if block['file_data']['filename'] == filename:
                file_block = block
                break
        
        if file_block and file_block['file_data']['file_hash'] == current_hash:
            flash('File integrity verified')
            return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)
        else:
            flash('File integrity check failed! The file may have been tampered with.')
            return redirect(url_for('index'))
    
    flash('File not found')
    return redirect(url_for('index'))

@app.route('/verify')
def verify_blockchain():
    is_valid = blockchain.is_chain_valid()
    if is_valid:
        flash('Blockchain integrity verified. All data is intact.')
    else:
        error_message = ', '.join(blockchain.validation_errors)
        flash(f'Blockchain integrity check failed! Issues detected: {error_message}')
    return redirect(url_for('index'))

@app.route('/repair')
def repair_blockchain():
    """Attempt to repair the blockchain"""
    if blockchain.is_chain_valid():
        flash('Blockchain is already valid. No repair needed.')
    else:
        original_errors = ', '.join(blockchain.validation_errors)
        blockchain.repair_chain()
        blockchain.save_to_file(app.config['BLOCKCHAIN_FILE'])
        
        if blockchain.is_chain_valid():
            flash(f'Blockchain has been successfully repaired. Previous issues: {original_errors}')
        else:
            flash(f'Failed to repair blockchain. Issues remain: {", ".join(blockchain.validation_errors)}')
    
    return redirect(url_for('index'))

@app.route('/reset')
def reset_blockchain():
    """Reset the blockchain to initial state"""
    blockchain.chain = []
    blockchain.create_genesis_block()
    blockchain.save_to_file(app.config['BLOCKCHAIN_FILE'])
    flash('Blockchain has been reset to initial state.')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)