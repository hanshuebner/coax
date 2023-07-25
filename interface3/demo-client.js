const axios = require('axios');
const crypto = require('crypto');

const API_ENDPOINT = 'http://192.168.1.143/demo';

async function sendPOSTRequest() {
    try {
        const response = await axios.post(API_ENDPOINT, "")
        if (response.status === 200) {
            return true
        } else {
            console.error('Error: failed.')
            return false
        }
    } catch (error) {
        console.error('Error:', error.message)
        return false
    }
}

async function main() {
    const WORDS_LENGTH = 8

    while (true) {
        const isSuccess = await sendPOSTRequest()
        if (!isSuccess) {
            break
        }
    }
}

main()
